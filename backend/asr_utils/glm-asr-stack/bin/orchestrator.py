#!/usr/bin/env python3
"""
Long-audio ASR + forced-alignment pipeline.

The orchestrator owns task-level work:
  1. decode input audio once to mono 16 kHz int16 WAV
  2. split it into <=30s WAV chunks
  3. batch-transcribe chunks through Infer-engine daemon
  4. align each chunk through forcealigner-engine daemon
  5. write transcript TSV and SRT
"""

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import traceback
import wave
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace


SEGMENT_SEC = 30.0
OVERLAP_SEC = 0.0
SAMPLE_RATE = 16000
ENGINE_BIN = str(Path(__file__).resolve().parents[1] / "bin" / "glm_asr_infer")
FA_BIN = str(Path(__file__).resolve().parents[1] / "bin" / "force_aligner")
FA_DIR = Path(FA_BIN).parent
BASE_DIR = Path(__file__).resolve().parents[1] / "runtime"
WORK_DIR = BASE_DIR / "work_dir"
OUTPUT_DIR = BASE_DIR / "output"
TASKS_DIR = BASE_DIR / "tasks"
LIVE_DIR = BASE_DIR / "live_sessions"
ASR_WINDOW_CHUNKS = 256
DEFAULT_ENGINE_ENV = {
    "GLMASR_VRAM_UTIL": "0.9",
    "GLMASR_MAX_SEQS": "256",
    "GLMASR_MAX_BATCHED_TOKENS": "10000",
    "GLMASR_MAX_NEW_TOKENS": "256",
    "GLMASR_ENCODER_FA_PIPELINED": "1",
    "GLMASR_ENCODER_FA_VLLM": "1",
    "GLMASR_ENCODER_FA_LONG_MIN_SEQ": "1",
    "GLMASR_ENCODER_FA_MIN_SEQ": "1",
}


def file_md5(path: str, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(path)


def read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def update_status(task_dir: Path | None, **fields) -> None:
    if task_dir is None:
        return
    status_path = task_dir / "status.json"
    status = read_json(status_path) if status_path.exists() else {}
    status.update(fields)
    status["updated_at"] = now_iso()
    write_json_atomic(status_path, status)


class TaskLogger:
    def __init__(self, log_path: Path, quiet: bool = False):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(log_path, "a", encoding="utf-8")
        self.quiet = quiet

    def log(self, message: str) -> None:
        line = f"{message}"
        if not self.quiet:
            print(line, flush=True)
        self.file.write(line + "\n")
        self.file.flush()

    def close(self) -> None:
        self.file.close()


def require_model_dir(path: str, label: str) -> None:
    if not path:
        raise SystemExit(f"ERROR: --{label} is empty; set the variable or pass the model path directly")
    config_path = Path(path) / "config.json"
    if not config_path.exists():
        raise SystemExit(f"ERROR: --{label} does not look like a model dir: missing {config_path}")


def require_file(path: str, label: str) -> None:
    if not path:
        raise SystemExit(f"ERROR: --{label} is empty; set the variable or pass the file path directly")
    if not Path(path).exists():
        raise SystemExit(f"ERROR: --{label} does not exist: {path}")


def prompt_text_from_args(args) -> str:
    prompt_parts = []
    prompt = getattr(args, "prompt", None)
    prompt_file = getattr(args, "prompt_file", None)
    if prompt:
        prompt_parts.append(prompt)
    if prompt_file:
        path = Path(prompt_file)
        if not path.exists():
            raise SystemExit(f"ERROR: --prompt-file does not exist: {prompt_file}")
        prompt_parts.append(path.read_text(encoding="utf-8").strip())
    return "\n".join(part for part in prompt_parts if part).strip()


@lru_cache(maxsize=4)
def get_hf_tokenizer(model_dir: str):
    os.environ.setdefault("USE_TORCH", "0")
    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("USE_FLAX", "0")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise SystemExit(
            "ERROR: --prompt requires transformers/tokenizers in the Python environment. "
            "Install with: pip install transformers tokenizers sentencepiece"
        ) from exc
    return AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)


def tokenize_user_prompt(model_dir: str, prompt_text: str) -> list[int]:
    if not prompt_text:
        return []
    tokenizer = get_hf_tokenizer(str(Path(model_dir).expanduser().resolve()))
    ids = tokenizer.encode(prompt_text, add_special_tokens=False)
    if len(ids) > 512:
        raise SystemExit(f"ERROR: prompt is too long after tokenization: {len(ids)} tokens > 512")
    return [int(x) for x in ids]


def is_native_wav(input_path: str) -> bool:
    try:
        with wave.open(str(input_path), "rb") as src:
            return (
                src.getnchannels() == 1
                and src.getsampwidth() == 2
                and src.getframerate() == SAMPLE_RATE
            )
    except (wave.Error, OSError, EOFError):
        return False


def copy_wav_native(input_path: str, wav_path: Path) -> Path:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = wav_path.with_name(wav_path.stem + ".tmp.wav")
    if tmp_path.exists():
        tmp_path.unlink()
    with wave.open(str(input_path), "rb") as src:
        if src.getnchannels() != 1 or src.getsampwidth() != 2 or src.getframerate() != SAMPLE_RATE:
            raise RuntimeError(f"unexpected WAV format for {input_path}")
        with wave.open(str(tmp_path), "wb") as dst:
            dst.setnchannels(1)
            dst.setsampwidth(2)
            dst.setframerate(SAMPLE_RATE)
            while True:
                frames = src.readframes(SAMPLE_RATE * 8)
                if not frames:
                    break
                dst.writeframes(frames)
    tmp_path.replace(wav_path)
    return wav_path


def decode_to_wav(input_path: str, audio_dir: Path) -> Path:
    """Decode any input audio to one mono 16 kHz int16 WAV."""
    audio_dir.mkdir(parents=True, exist_ok=True)
    wav_path = audio_dir / "source_16k_mono.wav"
    if wav_path.exists() and wav_path.stat().st_size > 44:
        return wav_path
    if is_native_wav(input_path):
        return copy_wav_native(input_path, wav_path)

    tmp_path = audio_dir / "source_16k_mono.tmp.wav"
    if tmp_path.exists():
        tmp_path.unlink()

    run([
        "ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", input_path,
        "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-acodec", "pcm_s16le",
        str(tmp_path),
    ])
    tmp_path.replace(wav_path)
    return wav_path


def decode_to_wav_file(input_path: str, wav_path: Path) -> Path:
    """Decode one input audio segment to a specific mono 16 kHz int16 WAV path."""
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    if is_native_wav(input_path):
        return copy_wav_native(input_path, wav_path)

    tmp_path = wav_path.with_name(wav_path.stem + ".tmp.wav")
    if tmp_path.exists():
        tmp_path.unlink()

    run([
        "ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", input_path,
        "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-acodec", "pcm_s16le",
        str(tmp_path),
    ])
    tmp_path.replace(wav_path)
    return wav_path


def wav_duration_sec(wav_path: Path) -> float:
    with wave.open(str(wav_path), "rb") as src:
        sample_rate = src.getframerate()
        if src.getnchannels() != 1 or src.getsampwidth() != 2 or sample_rate != SAMPLE_RATE:
            raise RuntimeError(f"unexpected WAV format for {wav_path}")
        return src.getnframes() / sample_rate


def split_wav(source_wav: Path, chunk_dir: Path, segment_sec: float, overlap_sec: float) -> list[dict]:
    """Split source WAV into int16 WAV chunks and return metadata."""
    if overlap_sec < 0 or overlap_sec >= segment_sec:
        raise ValueError("--overlap-sec must be >=0 and < --segment-sec")

    chunk_dir.mkdir(parents=True, exist_ok=True)

    with wave.open(str(source_wav), "rb") as src:
        channels = src.getnchannels()
        sample_width = src.getsampwidth()
        sample_rate = src.getframerate()
        total_frames = src.getnframes()

        if channels != 1 or sample_width != 2 or sample_rate != SAMPLE_RATE:
            raise RuntimeError(
                f"unexpected WAV format channels={channels} width={sample_width} rate={sample_rate}"
            )

        segment_frames = int(round(segment_sec * sample_rate))
        stride_frames = int(round((segment_sec - overlap_sec) * sample_rate))
        min_tail_frames = int(round(0.5 * sample_rate))
        segments = []
        start_frame = 0
        idx = 0

        while start_frame + min_tail_frames < total_frames:
            end_frame = min(start_frame + segment_frames, total_frames)
            nframes = end_frame - start_frame
            out_path = chunk_dir / f"chunk_{idx:06d}.wav"

            if not out_path.exists() or out_path.stat().st_size <= 44:
                src.setpos(start_frame)
                frames = src.readframes(nframes)
                tmp_path = out_path.with_suffix(".wav.tmp")
                with wave.open(str(tmp_path), "wb") as dst:
                    dst.setnchannels(1)
                    dst.setsampwidth(2)
                    dst.setframerate(sample_rate)
                    dst.writeframes(frames)
                tmp_path.replace(out_path)

            segments.append({
                "idx": idx,
                "path": str(out_path),
                "start_sec": start_frame / sample_rate,
                "end_sec": end_frame / sample_rate,
                "duration_sec": nframes / sample_rate,
            })

            start_frame += stride_frames
            idx += 1

    total_sec = total_frames / SAMPLE_RATE
    print(f"[segmenter] {len(segments)} chunks from {total_sec:.1f}s audio")
    return segments


class InferDaemon:
    """Infer-engine daemon client."""

    def __init__(self, model_dir: str, mel_path: str, stderr=None):
        self.proc = subprocess.Popen(
            [ENGINE_BIN, "--daemon"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr if stderr is not None else sys.stderr,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env={**DEFAULT_ENGINE_ENV, **os.environ},
        )
        self._cmd(f"LOAD {model_dir}")
        self._wait_ready()
        self._cmd(f"MEL {mel_path}")
        self._wait_ready()

    def _cmd(self, line: str) -> None:
        if self.proc.stdin is None:
            raise RuntimeError("Infer-engine stdin is closed")
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def _readline(self) -> str:
        if self.proc.stdout is None:
            raise RuntimeError("Infer-engine stdout is closed")
        line = self.proc.stdout.readline()
        if line == "":
            raise RuntimeError("Infer-engine daemon exited unexpectedly")
        return line.rstrip("\n")

    def _wait_ready(self) -> None:
        while True:
            if self._readline() == "READY":
                return

    def transcribe_batch(self, paths: list[str], prompt_ids: list[int] | None = None) -> tuple[dict[str, str], float, int]:
        prompt_ids = prompt_ids or []
        if prompt_ids:
            self._cmd("PROMPT_IDS " + str(len(prompt_ids)) + " " + " ".join(str(x) for x in prompt_ids))
            self._wait_ready()
        else:
            self._cmd("PROMPT_IDS 0")
            self._wait_ready()
        self._cmd(f"BATCH {len(paths)}")
        for p in paths:
            self._cmd(p)
        self._cmd("RUN")

        results: dict[str, str] = {}
        infer_ms = 0.0
        output_tokens = 0

        while True:
            line = self._readline()
            if line == "READY":
                break
            if line.startswith("INFER_TIME:"):
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        infer_ms = float(parts[1])
                    except ValueError:
                        pass
                continue
            if line.startswith("OUTPUT_TOKENS:"):
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        output_tokens = int(parts[1])
                    except ValueError:
                        pass
                continue
            if ": " in line:
                path, text = line.split(": ", 1)
                results[path] = text

        return results, infer_ms, output_tokens

    def close(self) -> None:
        try:
            self._cmd("QUIT")
        except Exception:
            pass
        self.proc.wait(timeout=30)


class FADaemon:
    """ForceAligner daemon client."""

    def __init__(self, model_dir: str, stderr=None):
        self.proc = subprocess.Popen(
            [FA_BIN, "--model", model_dir, "--daemon"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr if stderr is not None else sys.stderr,
            cwd=str(FA_DIR),
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

    def align_one(self, audio_path: str, text: str, lang: str) -> list[dict]:
        if self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("ForceAligner daemon pipe is closed")

        self.proc.stdin.write(f"{audio_path}\t{text}\t{lang}\n")
        self.proc.stdin.flush()

        words = []
        while True:
            line = self.proc.stdout.readline()
            if line == "":
                raise RuntimeError("ForceAligner daemon exited unexpectedly")
            line = line.rstrip("\n")
            if line == "":
                break
            parts = line.split("\t")
            if len(parts) >= 3:
                words.append({
                    "text": parts[0],
                    "start": float(parts[1]),
                    "end": float(parts[2]),
                })
        return words

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.wait(timeout=30)


class InferDaemonPool:
    def __init__(self):
        self.items = {}
        self.worker_log_dir = TASKS_DIR / "worker_logs"
        self.worker_log_dir.mkdir(parents=True, exist_ok=True)

    def get(self, model_dir: str, mel_path: str):
        key = (model_dir, mel_path)
        item = self.items.get(key)
        if item is not None:
            return item["daemon"], item["stderr_path"]

        stderr_path = self.worker_log_dir / f"infer_persistent_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.stderr.log"
        stderr_file = open(stderr_path, "a", encoding="utf-8")
        daemon = InferDaemon(model_dir, mel_path, stderr=stderr_file)
        item = {
            "daemon": daemon,
            "stderr_file": stderr_file,
            "stderr_path": stderr_path,
        }
        self.items[key] = item
        return daemon, stderr_path

    def close_all(self) -> None:
        for item in self.items.values():
            try:
                item["daemon"].close()
            finally:
                item["stderr_file"].close()
        self.items.clear()


def write_transcripts_tsv(
    segments: list[dict],
    texts: dict[str, str],
    output_path: Path,
    include_missing: bool = True,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["segment_id", "start_s", "end_s", "duration_s", "audio_path", "text"])
        for seg in segments:
            if not include_missing and seg["path"] not in texts:
                continue
            writer.writerow([
                seg["idx"],
                f"{seg['start_sec']:.3f}",
                f"{seg['end_sec']:.3f}",
                f"{seg['duration_sec']:.3f}",
                seg["path"],
                texts.get(seg["path"], ""),
            ])


def read_transcripts_tsv(input_path: Path) -> dict[str, str]:
    texts: dict[str, str] = {}
    with open(input_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            audio_path = row.get("audio_path", "")
            if audio_path:
                texts[audio_path] = row.get("text", "")
    return texts


def split_sentences(text: str) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []

    parts = re.findall(r"[^.!?。！？]+[.!?。！？]+[\"')\]”’]*|[^.!?。！？]+$", text)
    sentences = [part.strip() for part in parts if part.strip()]
    return sentences if sentences else [text]


def norm_terms(text: str) -> list[str]:
    terms = []
    for match in re.finditer(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?|[\u4e00-\u9fff]", text.lower()):
        token = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", match.group())
        if token:
            terms.append(token)
    return terms


def sentence_cues_for_segment(seg: dict) -> list[dict]:
    words = seg["words"]
    if not words:
        return []

    word_terms = [norm_terms(word["text"]) for word in words]
    word_norms = [terms[0] if terms else "" for terms in word_terms]
    cursor = 0
    cues = []

    for sentence in split_sentences(seg.get("text", "")):
        terms = norm_terms(sentence)
        if not terms:
            continue

        start_idx = None
        end_idx = None
        search_from = cursor
        matched = 0

        for term in terms:
            found = None
            for idx in range(search_from, len(word_norms)):
                if word_norms[idx] == term:
                    found = idx
                    break
            if found is not None:
                if start_idx is None:
                    start_idx = found
                end_idx = found
                search_from = found + 1
                matched += 1

        if start_idx is None or end_idx is None or matched < max(1, len(terms) // 2):
            start_idx = min(cursor, len(words) - 1)
            end_idx = min(start_idx + max(0, len(terms) - 1), len(words) - 1)
            search_from = end_idx + 1

        cues.append({
            "text": sentence,
            "start": seg["start_sec"] + words[start_idx]["start"],
            "end": seg["start_sec"] + words[end_idx]["end"],
        })
        cursor = min(search_from, len(words))

    return cues


def merge_to_srt(aligned_segments: list[dict], output_path: Path, subtitle_mode: str) -> None:
    cues = []
    seen_end = -1.0

    if subtitle_mode == "word":
        for seg in aligned_segments:
            offset = seg["start_sec"]
            for word in seg["words"]:
                cues.append({
                    "text": word["text"],
                    "start": offset + word["start"],
                    "end": offset + word["end"],
                })
    elif subtitle_mode == "sentence":
        for seg in aligned_segments:
            cues.extend(sentence_cues_for_segment(seg))
    else:
        raise ValueError(f"unknown subtitle mode: {subtitle_mode}")

    filtered_cues = []
    for cue in cues:
        start = cue["start"]
        end = cue["end"]
        if end <= seen_end + 0.05:
            continue
        if start < seen_end:
            start = seen_end
        filtered_cues.append({"text": cue["text"], "start": start, "end": end})
        seen_end = max(seen_end, end)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for i, cue in enumerate(filtered_cues, 1):
            f.write(f"{i}\n{sec_to_srt(cue['start'])} --> {sec_to_srt(cue['end'])}\n")
            f.write(f"{cue['text']}\n\n")

    print(f"[srt] wrote {len(filtered_cues)} {subtitle_mode} cues to {output_path}")


def merge_words_to_srt(aligned_segments: list[dict], output_path: Path) -> None:
    global_words = []
    seen_end = -1.0

    for seg in aligned_segments:
        offset = seg["start_sec"]
        for word in seg["words"]:
            start = offset + word["start"]
            end = offset + word["end"]
            if end <= seen_end + 0.05:
                continue
            global_words.append({"text": word["text"], "start": start, "end": end})
            seen_end = max(seen_end, end)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for i, word in enumerate(global_words, 1):
            f.write(f"{i}\n{sec_to_srt(word['start'])} --> {sec_to_srt(word['end'])}\n")
            f.write(f"{word['text']}\n\n")

    print(f"[srt] wrote {len(global_words)} words to {output_path}")


def sec_to_srt(sec: float) -> str:
    if sec < 0:
        sec = 0.0
    hours = int(sec // 3600)
    minutes = int((sec % 3600) // 60)
    seconds = int(sec % 60)
    millis = int(round((sec - int(sec)) * 1000))
    if millis >= 1000:
        seconds += 1
        millis -= 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def default_output_path(audio: str, subtitle_mode: str) -> Path:
    suffix = "" if subtitle_mode == "word" else f"_{subtitle_mode}"
    return OUTPUT_DIR / f"{Path(audio).stem}{suffix}.srt"


def task_id_for(audio: str, explicit_id: str | None = None) -> str:
    if explicit_id:
        return explicit_id
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(audio).stem)[:48]
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{stem}_{file_md5(audio)[:8]}"


def args_to_task(args) -> dict:
    output = args.output or str(default_output_path(args.audio, args.subtitle_mode))
    return {
        "audio": args.audio,
        "model": args.model,
        "mel": args.mel,
        "fa_model": args.fa_model,
        "lang": args.lang,
        "output": output,
        "batch_size": args.batch_size,
        "segment_sec": args.segment_sec,
        "overlap_sec": args.overlap_sec,
        "subtitle_mode": args.subtitle_mode,
        "asr_only": args.asr_only,
        "reuse_asr": args.reuse_asr,
        "prompt": prompt_text_from_args(args),
    }


def task_to_args(task: dict):
    return SimpleNamespace(
        audio=task["audio"],
        model=task["model"],
        mel=task["mel"],
        fa_model=task["fa_model"],
        lang=task.get("lang", "English"),
        output=task.get("output"),
        batch_size=int(task.get("batch_size", 128)),
        segment_sec=float(task.get("segment_sec", SEGMENT_SEC)),
        overlap_sec=float(task.get("overlap_sec", OVERLAP_SEC)),
        subtitle_mode=task.get("subtitle_mode", "word"),
        asr_only=bool(task.get("asr_only", False)),
        reuse_asr=bool(task.get("reuse_asr", False)),
        prompt=task.get("prompt", ""),
        prompt_file=None,
        quiet=bool(task.get("quiet", False)),
    )


def submit_task(args) -> Path:
    require_file(args.audio, "audio")
    require_model_dir(args.model, "model")
    require_file(args.mel, "mel")
    if not args.asr_only:
        require_model_dir(args.fa_model, "fa-model")

    tid = task_id_for(args.audio, args.task_id)
    task_dir = TASKS_DIR / tid
    if task_dir.exists() and args.task_id:
        raise SystemExit(f"ERROR: task already exists: {task_dir}")
    suffix = 1
    base_tid = tid
    while task_dir.exists():
        tid = f"{base_tid}_{suffix}"
        task_dir = TASKS_DIR / tid
        suffix += 1

    task = args_to_task(args)
    task["task_id"] = tid
    task["created_at"] = now_iso()
    task["input_md5"] = file_md5(args.audio)

    write_json_atomic(task_dir / "task.json", task)
    write_json_atomic(task_dir / "status.json", {
        "task_id": tid,
        "state": "queued",
        "created_at": task["created_at"],
        "updated_at": task["created_at"],
    })
    print(task_dir)
    return task_dir


def resolve_task_dir(value: str) -> Path:
    path = Path(value)
    if path.exists():
        return path
    return TASKS_DIR / value


def queued_tasks() -> list[Path]:
    return tasks_by_state({"queued"})


def tasks_by_state(states: set[str]) -> list[Path]:
    tasks = []
    if not TASKS_DIR.exists():
        return tasks
    for status_path in sorted(TASKS_DIR.glob("*/status.json")):
        try:
            status = read_json(status_path)
        except Exception:
            continue
        if status.get("state") in states:
            tasks.append(status_path.parent)
    return tasks


def runtime_paths(args):
    input_md5 = file_md5(args.audio)
    run_dir = WORK_DIR / input_md5
    return SimpleNamespace(
        input_md5=input_md5,
        run_dir=run_dir,
        audio_dir=run_dir / "audio",
        chunk_dir=run_dir / "chunks",
        asr_dir=run_dir / "asr",
        transcript_tsv=run_dir / "asr" / "transcript_by_chunk.tsv",
        output_path=Path(args.output) if args.output else default_output_path(args.audio, args.subtitle_mode),
    )


def prepare_segments(args, paths, logger: TaskLogger) -> list[dict]:
    logger.log(f"[task] audio={args.audio}")
    logger.log(f"[task] md5={paths.input_md5}")
    logger.log(f"[task] work_dir={paths.run_dir}")
    source_wav = decode_to_wav(args.audio, paths.audio_dir)
    segments = split_wav(source_wav, paths.chunk_dir, args.segment_sec, args.overlap_sec)
    logger.log(f"[segmenter] {len(segments)} chunks")
    return segments


def task_group_key(task: dict) -> tuple:
    return (
        task["model"],
        task["mel"],
        int(task.get("batch_size", 128)),
        float(task.get("segment_sec", SEGMENT_SEC)),
        float(task.get("overlap_sec", OVERLAP_SEC)),
        task.get("prompt", ""),
    )


def mark_task_failed(task_dir: Path, logger: TaskLogger | None, exc: Exception) -> None:
    update_status(task_dir, state="failed", error=str(exc), traceback=traceback.format_exc(), failed_at=now_iso())
    if logger is not None:
        logger.log(f"[error] {exc}")
        logger.log(traceback.format_exc())


def run_asr_stage(task_dirs: list[Path], max_chunks: int, infer_pool: InferDaemonPool | None = None) -> None:
    max_chunks = max(1, max_chunks)
    groups: dict[tuple, list[Path]] = {}
    for task_dir in task_dirs:
        task = read_json(task_dir / "task.json")
        groups.setdefault(task_group_key(task), []).append(task_dir)

    worker_log_dir = TASKS_DIR / "worker_logs"
    worker_log_dir.mkdir(parents=True, exist_ok=True)

    for key, group_task_dirs in groups.items():
        model_dir, mel_path, batch_size, _, _, prompt_text = key
        require_model_dir(model_dir, "model")
        require_file(mel_path, "mel")
        prompt_ids = tokenize_user_prompt(model_dir, prompt_text)

        infos = []
        all_items = []
        loggers: list[TaskLogger] = []

        try:
            for task_dir in group_task_dirs:
                task = read_json(task_dir / "task.json")
                args = task_to_args(task)
                paths = runtime_paths(args)
                logger = TaskLogger(task_dir / "logs" / "orchestrator.log", quiet=args.quiet)
                loggers.append(logger)
                update_status(task_dir, state="running", phase="asr", started_at=now_iso())

                try:
                    require_file(args.audio, "audio")
                    if not args.asr_only:
                        require_model_dir(args.fa_model, "fa-model")
                    segments = prepare_segments(args, paths, logger)
                    update_status(task_dir, phase="asr", chunks_total=len(segments), asr_chunks_done=0)

                    texts = read_transcripts_tsv(paths.transcript_tsv) if paths.transcript_tsv.exists() else {}
                    completed_paths = {seg["path"] for seg in segments if seg["path"] in texts}
                    is_complete = len(completed_paths) == len(segments)

                    if is_complete and (args.reuse_asr or texts):
                        logger.log(f"[asr] using complete transcript {len(texts)} chunks from {paths.transcript_tsv}")
                        result = {
                            "transcript_tsv": str(paths.transcript_tsv),
                            "output": None if args.asr_only else str(paths.output_path),
                            "chunks": len(segments),
                            "asr_chunks": len(texts),
                            "asr_infer_sec": 0.0,
                            "asr_wall_sec": 0.0,
                            "output_tokens": 0,
                        }
                        if args.asr_only:
                            update_status(
                                task_dir,
                                state="completed",
                                phase="done",
                                asr_chunks_done=len(texts),
                                asr_reused=True,
                                result=result,
                                completed_at=now_iso(),
                            )
                        else:
                            update_status(
                                task_dir,
                                state="align_queued",
                                phase="align_queued",
                                asr_chunks_done=len(texts),
                                asr_reused=True,
                                result=result,
                        )
                        continue

                    pending_segments = [seg for seg in segments if seg["path"] not in texts]
                    previous_result = read_json(task_dir / "status.json").get("result", {})
                    info = {
                        "task_dir": task_dir,
                        "task": task,
                        "args": args,
                        "paths": paths,
                        "logger": logger,
                        "segments": segments,
                        "pending_segments": pending_segments,
                        "texts": texts,
                        "infer_ms": float(previous_result.get("asr_infer_sec", 0.0)) * 1000.0,
                        "output_tokens": int(previous_result.get("output_tokens", 0)),
                        "previous_asr_wall": float(previous_result.get("asr_wall_sec", 0.0)),
                        "asr_start": time.time(),
                    }
                    infos.append(info)
                except Exception as exc:
                    mark_task_failed(task_dir, logger, exc)

            while len(all_items) < max_chunks:
                progressed = False
                for info in infos:
                    idx = info.setdefault("window_cursor", 0)
                    pending = info["pending_segments"]
                    if idx >= len(pending):
                        continue
                    all_items.append((info, pending[idx]))
                    info["window_cursor"] = idx + 1
                    progressed = True
                    if len(all_items) >= max_chunks:
                        break
                if not progressed:
                    break

            if not all_items:
                continue

            if infer_pool is not None:
                infer, stderr_path = infer_pool.get(model_dir, mel_path)
                close_infer = False
            else:
                stderr_path = worker_log_dir / f"infer_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.stderr.log"
                infer_stderr = open(stderr_path, "a", encoding="utf-8")
                infer = InferDaemon(model_dir, mel_path, stderr=infer_stderr)
                close_infer = True

            print(f"[asr-stage] {len(infos)} tasks, {len(all_items)} chunks window, stderr={stderr_path}")
            try:
                for start in range(0, len(all_items), batch_size):
                    batch = all_items[start:start + batch_size]
                    paths = [seg["path"] for _, seg in batch]
                    results, infer_ms, output_tokens = infer.transcribe_batch(paths, prompt_ids=prompt_ids)

                    touched = {}
                    for info, seg in batch:
                        text = results.get(seg["path"], "")
                        info["texts"][seg["path"]] = text
                        touched[info["task_dir"]] = info

                    token_share = output_tokens / max(1, len(batch))
                    infer_share = infer_ms / max(1, len(batch))
                    for info, _seg in batch:
                        info["infer_ms"] += infer_share
                        info["output_tokens"] += int(round(token_share))

                    for info in touched.values():
                        done = len(info["texts"])
                        info["logger"].log(
                            f"[asr-stage] progress {done}/{len(info['segments'])} chunks"
                        )
                        update_status(
                            info["task_dir"],
                            phase="asr",
                            asr_chunks_done=done,
                            chunks_total=len(info["segments"]),
                            asr_infer_sec=info["infer_ms"] / 1000.0,
                            output_tokens=info["output_tokens"],
                        )
            finally:
                if close_infer:
                    try:
                        infer.close()
                    finally:
                        infer_stderr.close()

            for info in infos:
                args = info["args"]
                paths = info["paths"]
                segments = info["segments"]
                texts = info["texts"]
                asr_wall = info["previous_asr_wall"] + (time.time() - info["asr_start"])
                is_complete = len({seg["path"] for seg in segments if seg["path"] in texts}) == len(segments)
                write_transcripts_tsv(segments, texts, paths.transcript_tsv, include_missing=is_complete)
                info["logger"].log(f"[asr] transcribed {len(texts)}/{len(segments)} chunks")
                info["logger"].log(
                    f"[asr] infer_time={info['infer_ms'] / 1000.0:.2f}s "
                    f"wall={asr_wall:.2f}s output_tokens={info['output_tokens']}"
                )
                info["logger"].log(f"[asr] wrote {paths.transcript_tsv}")
                result = {
                    "transcript_tsv": str(paths.transcript_tsv),
                    "output": None if args.asr_only else str(paths.output_path),
                    "chunks": len(segments),
                    "asr_chunks": len(texts),
                    "asr_infer_sec": info["infer_ms"] / 1000.0,
                    "asr_wall_sec": asr_wall,
                    "output_tokens": info["output_tokens"],
                }
                if not is_complete:
                    update_status(
                        info["task_dir"],
                        state="queued",
                        phase="asr",
                        asr_chunks_done=len(texts),
                        chunks_total=len(segments),
                        result=result,
                    )
                elif args.asr_only:
                    update_status(info["task_dir"], state="completed", phase="done", result=result, completed_at=now_iso())
                else:
                    update_status(info["task_dir"], state="align_queued", phase="align_queued", result=result)
        except Exception as exc:
            for task_dir in group_task_dirs:
                status = read_json(task_dir / "status.json")
                if status.get("state") == "running":
                    mark_task_failed(task_dir, None, exc)
            raise
        finally:
            for logger in loggers:
                logger.close()


def run_align_stage(task_dir: Path) -> None:
    task = read_json(task_dir / "task.json")
    args = task_to_args(task)
    paths = runtime_paths(args)
    logger = TaskLogger(task_dir / "logs" / "orchestrator.log", quiet=args.quiet)

    try:
        require_file(args.audio, "audio")
        require_model_dir(args.fa_model, "fa-model")
        if not paths.transcript_tsv.exists():
            raise RuntimeError(f"missing ASR transcript TSV: {paths.transcript_tsv}")

        update_status(task_dir, state="running", phase="align", align_chunks_done=0)
        segments = prepare_segments(args, paths, logger)
        texts = read_transcripts_tsv(paths.transcript_tsv)

        logger.log("[align] starting ForceAligner daemon")
        aligned_segments = []
        t0 = time.time()
        with open(task_dir / "logs" / "aligner.stderr.log", "a", encoding="utf-8") as align_stderr:
            fa = FADaemon(args.fa_model, stderr=align_stderr)
            try:
                for seg in segments:
                    text = texts.get(seg["path"], "")
                    if not text or text == "[ERROR]":
                        continue
                    words = fa.align_one(seg["path"], text, args.lang)
                    aligned_segments.append({"start_sec": seg["start_sec"], "text": text, "words": words})
                    logger.log(f"[align] chunk {seg['idx']:06d}: {len(words)} words | {text[:80]}")
                    if len(aligned_segments) % 10 == 0 or len(aligned_segments) == len(segments):
                        update_status(
                            task_dir,
                            phase="align",
                            align_chunks_done=len(aligned_segments),
                            align_chunks_total=len(segments),
                        )
            finally:
                fa.close()

        align_wall = time.time() - t0
        logger.log(f"[align] aligned {len(aligned_segments)}/{len(segments)} chunks wall={align_wall:.2f}s")
        merge_to_srt(aligned_segments, paths.output_path, args.subtitle_mode)
        logger.log(f"[done] {paths.output_path}")

        previous_result = read_json(task_dir / "status.json").get("result", {})
        result = {
            **previous_result,
            "output": str(paths.output_path),
            "aligned_chunks": len(aligned_segments),
            "align_wall_sec": align_wall,
            "subtitle_mode": args.subtitle_mode,
        }
        update_status(task_dir, state="completed", phase="done", result=result, completed_at=now_iso())
    except Exception as exc:
        mark_task_failed(task_dir, logger, exc)
        raise
    finally:
        logger.close()


def run_pipeline(args, task_dir: Path | None = None) -> dict:
    require_file(args.audio, "audio")

    input_md5 = file_md5(args.audio)
    run_dir = WORK_DIR / input_md5
    audio_dir = run_dir / "audio"
    chunk_dir = run_dir / "chunks"
    asr_dir = run_dir / "asr"
    logs_dir = (task_dir / "logs") if task_dir is not None else (run_dir / "logs")

    output_path = Path(args.output) if args.output else default_output_path(args.audio, args.subtitle_mode)
    transcript_tsv = asr_dir / "transcript_by_chunk.tsv"
    logger = TaskLogger(logs_dir / "orchestrator.log", quiet=getattr(args, "quiet", False))

    try:
        if not args.reuse_asr or not transcript_tsv.exists():
            require_model_dir(args.model, "model")
            require_file(args.mel, "mel")
        if not args.asr_only:
            require_model_dir(args.fa_model, "fa-model")
        prompt_text = prompt_text_from_args(args)
        prompt_ids = tokenize_user_prompt(args.model, prompt_text)

        update_status(task_dir, state="running", started_at=now_iso(), phase="segmenting")

        logger.log(f"[task] audio={args.audio}")
        logger.log(f"[task] md5={input_md5}")
        logger.log(f"[task] work_dir={run_dir}")
        logger.log(f"[task] logs_dir={logs_dir}")
        if prompt_ids:
            logger.log(f"[prompt] {len(prompt_ids)} tokens")

        source_wav = decode_to_wav(args.audio, audio_dir)
        segments = split_wav(source_wav, chunk_dir, args.segment_sec, args.overlap_sec)
        logger.log(f"[segmenter] {len(segments)} chunks")
        update_status(task_dir, phase="asr", chunks_total=len(segments))

        texts: dict[str, str] = {}
        total_infer_ms = 0.0
        total_output_tokens = 0

        if args.reuse_asr and transcript_tsv.exists():
            texts = read_transcripts_tsv(transcript_tsv)
            asr_wall = 0.0
            logger.log(f"[asr] reused {len(texts)} transcripts from {transcript_tsv}")
            update_status(task_dir, asr_chunks_done=len(texts), asr_reused=True)
        else:
            logger.log("[asr] starting Infer-engine daemon")
            t0 = time.time()
            with open(logs_dir / "infer.stderr.log", "a", encoding="utf-8") as infer_stderr:
                infer = InferDaemon(args.model, args.mel, stderr=infer_stderr)
                try:
                    for start in range(0, len(segments), args.batch_size):
                        batch = segments[start:start + args.batch_size]
                        paths = [seg["path"] for seg in batch]
                        results, infer_ms, output_tokens = infer.transcribe_batch(paths, prompt_ids=prompt_ids)
                        texts.update(results)
                        total_infer_ms += infer_ms
                        total_output_tokens += output_tokens
                        batch_no = start // args.batch_size + 1
                        logger.log(
                            f"[asr] batch {batch_no}: "
                            f"{len(results)}/{len(batch)} chunks, infer={infer_ms / 1000.0:.2f}s, "
                            f"tokens={output_tokens}"
                        )
                        update_status(
                            task_dir,
                            phase="asr",
                            asr_chunks_done=len(texts),
                            asr_infer_sec=total_infer_ms / 1000.0,
                            output_tokens=total_output_tokens,
                        )
                finally:
                    infer.close()
            asr_wall = time.time() - t0

            write_transcripts_tsv(segments, texts, transcript_tsv)
            logger.log(f"[asr] transcribed {len(texts)}/{len(segments)} chunks")
            logger.log(
                f"[asr] infer_time={total_infer_ms / 1000.0:.2f}s "
                f"wall={asr_wall:.2f}s output_tokens={total_output_tokens}"
            )
            logger.log(f"[asr] wrote {transcript_tsv}")

        if args.asr_only:
            result = {
                "transcript_tsv": str(transcript_tsv),
                "output": None,
                "chunks": len(segments),
                "asr_chunks": len(texts),
                "asr_infer_sec": total_infer_ms / 1000.0,
                "asr_wall_sec": asr_wall,
                "output_tokens": total_output_tokens,
            }
            update_status(task_dir, state="completed", phase="done", result=result, completed_at=now_iso())
            return result

        logger.log("[align] starting ForceAligner daemon")
        update_status(task_dir, phase="align", align_chunks_done=0)
        aligned_segments = []
        t1 = time.time()
        with open(logs_dir / "aligner.stderr.log", "a", encoding="utf-8") as align_stderr:
            fa = FADaemon(args.fa_model, stderr=align_stderr)
            try:
                for seg in segments:
                    text = texts.get(seg["path"], "")
                    if not text or text == "[ERROR]":
                        continue
                    words = fa.align_one(seg["path"], text, args.lang)
                    aligned_segments.append({"start_sec": seg["start_sec"], "text": text, "words": words})
                    logger.log(f"[align] chunk {seg['idx']:06d}: {len(words)} words | {text[:80]}")
                    if len(aligned_segments) % 10 == 0 or len(aligned_segments) == len(segments):
                        update_status(
                            task_dir,
                            phase="align",
                            align_chunks_done=len(aligned_segments),
                            align_chunks_total=len(segments),
                        )
            finally:
                fa.close()
        align_wall = time.time() - t1
        logger.log(f"[align] aligned {len(aligned_segments)}/{len(segments)} chunks wall={align_wall:.2f}s")

        merge_to_srt(aligned_segments, output_path, args.subtitle_mode)
        logger.log(f"[done] {output_path}")

        result = {
            "transcript_tsv": str(transcript_tsv),
            "output": str(output_path),
            "chunks": len(segments),
            "asr_chunks": len(texts),
            "aligned_chunks": len(aligned_segments),
            "asr_infer_sec": total_infer_ms / 1000.0,
            "asr_wall_sec": asr_wall,
            "align_wall_sec": align_wall,
            "output_tokens": total_output_tokens,
            "subtitle_mode": args.subtitle_mode,
        }
        update_status(task_dir, state="completed", phase="done", result=result, completed_at=now_iso())
        return result
    except Exception as exc:
        update_status(task_dir, state="failed", error=str(exc), traceback=traceback.format_exc(), failed_at=now_iso())
        logger.log(f"[error] {exc}")
        logger.log(traceback.format_exc())
        raise
    finally:
        logger.close()


def run_task(task_dir: Path) -> dict:
    task_path = task_dir / "task.json"
    if not task_path.exists():
        raise SystemExit(f"ERROR: missing task.json: {task_path}")
    status_path = task_dir / "status.json"
    status = read_json(status_path) if status_path.exists() else {}
    if status.get("state") == "running":
        raise SystemExit(f"ERROR: task is already marked running: {task_dir}")

    task = read_json(task_path)
    status.update({
        "task_id": task.get("task_id", task_dir.name),
        "state": "running",
        "updated_at": now_iso(),
    })
    write_json_atomic(status_path, status)
    return run_pipeline(task_to_args(task), task_dir=task_dir)


def run_queue(once: bool, asr_window_chunks: int) -> None:
    infer_pool = InferDaemonPool()
    try:
        while True:
            tasks = queued_tasks()
            if tasks:
                print(f"[queue] ASR stage: {len(tasks)} queued tasks")
                run_asr_stage(tasks, asr_window_chunks, infer_pool=infer_pool)
                if once:
                    return
                continue

            align_tasks = tasks_by_state({"align_queued"})
            if align_tasks:
                task_dir = align_tasks[0]
                print(f"[queue] align stage: {task_dir}")
                run_align_stage(task_dir)
                if once:
                    return
                continue

            print("[queue] no queued tasks")
            return
    finally:
        infer_pool.close_all()


def print_task_status(value: str) -> None:
    task_dir = resolve_task_dir(value)
    status_path = task_dir / "status.json"
    if not status_path.exists():
        raise SystemExit(f"ERROR: missing status.json: {status_path}")
    print(json.dumps(read_json(status_path), ensure_ascii=False, indent=2))


def validate_live_session_id(session_id: str) -> str:
    if not session_id or not re.fullmatch(r"[A-Za-z0-9_.-]+", session_id):
        raise SystemExit("ERROR: live session id must match [A-Za-z0-9_.-]+")
    return session_id


def live_session_dir(session_id: str) -> Path:
    return LIVE_DIR / validate_live_session_id(session_id)


def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_live_transcript_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def append_live_transcripts(output_path: Path, rows: list[dict]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    exists = output_path.exists() and output_path.stat().st_size > 0
    with open(output_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        if not exists:
            writer.writerow(["segment_id", "start_s", "end_s", "duration_s", "audio_path", "text"])
        for row in rows:
            writer.writerow([
                row["segment_id"],
                f"{row['start_sec']:.3f}",
                f"{row['end_sec']:.3f}",
                f"{row['duration_sec']:.3f}",
                row["audio_path"],
                row["text"],
            ])


def live_cues_for_text(text: str, start_sec: float, end_sec: float, subtitle_mode: str) -> list[dict]:
    text = " ".join(text.split())
    if not text:
        return []
    duration = max(0.05, end_sec - start_sec)

    if subtitle_mode == "word":
        units = re.findall(r"\S+", text)
    elif subtitle_mode == "sentence":
        units = split_sentences(text)
    else:
        raise ValueError(f"unknown subtitle mode: {subtitle_mode}")

    if not units:
        units = [text]
    weights = [max(1, len(norm_terms(unit)) or len(unit)) for unit in units]
    total_weight = max(1, sum(weights))
    cues = []
    cursor = start_sec
    for idx, unit in enumerate(units):
        if idx == len(units) - 1:
            cue_end = end_sec
        else:
            cue_end = cursor + duration * weights[idx] / total_weight
        cues.append({"text": unit, "start": cursor, "end": max(cursor + 0.05, cue_end)})
        cursor = cue_end
    return cues


def write_live_srt(rows: list[dict], output_path: Path, subtitle_mode: str) -> None:
    cues = []
    seen_end = -1.0
    for row in rows:
        try:
            start_sec = float(row["start_s"])
            end_sec = float(row["end_s"])
        except (KeyError, ValueError):
            continue
        for cue in live_cues_for_text(row.get("text", ""), start_sec, end_sec, subtitle_mode):
            start = max(cue["start"], seen_end)
            end = max(start + 0.05, cue["end"])
            cues.append({"text": cue["text"], "start": start, "end": end})
            seen_end = end

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for i, cue in enumerate(cues, 1):
            f.write(f"{i}\n{sec_to_srt(cue['start'])} --> {sec_to_srt(cue['end'])}\n")
            f.write(f"{cue['text']}\n\n")


def live_create(args) -> Path:
    session_dir = live_session_dir(args.live_create)
    if session_dir.exists():
        raise SystemExit(f"ERROR: live session already exists: {session_dir}")
    require_model_dir(args.model, "model")
    require_file(args.mel, "mel")

    output = args.output or str(OUTPUT_DIR / f"{args.live_create}_{args.subtitle_mode}.srt")
    session = {
        "session_id": args.live_create,
        "created_at": now_iso(),
        "model": args.model,
        "mel": args.mel,
        "lang": args.lang,
        "output": output,
        "batch_size": args.batch_size,
        "subtitle_mode": args.subtitle_mode,
        "prompt": prompt_text_from_args(args),
        "mode": "live_asr",
    }
    write_json_atomic(session_dir / "session.json", session)
    write_json_atomic(session_dir / "status.json", {
        "session_id": args.live_create,
        "state": "idle",
        "segments_total": 0,
        "segments_done": 0,
        "output": output,
        "created_at": session["created_at"],
        "updated_at": session["created_at"],
    })
    (session_dir / "segments").mkdir(parents=True, exist_ok=True)
    (session_dir / "logs").mkdir(parents=True, exist_ok=True)
    print(session_dir)
    return session_dir


def live_append(args) -> None:
    session_dir = live_session_dir(args.live_append)
    session_path = session_dir / "session.json"
    if not session_path.exists():
        raise SystemExit(f"ERROR: missing live session: {session_dir}")
    require_file(args.audio, "audio")

    segments_path = session_dir / "segments.jsonl"
    segments = read_jsonl(segments_path)
    next_id = max([int(seg["segment_id"]) for seg in segments], default=-1) + 1
    wav_path = session_dir / "segments" / f"segment_{next_id:06d}.wav"
    decode_to_wav_file(args.audio, wav_path)
    duration = wav_duration_sec(wav_path)

    if args.start_sec is None:
        start_sec = max([float(seg["end_sec"]) for seg in segments], default=0.0)
    else:
        start_sec = float(args.start_sec)
    end_sec = float(args.end_sec) if args.end_sec is not None else start_sec + duration
    if end_sec <= start_sec:
        end_sec = start_sec + duration

    row = {
        "segment_id": next_id,
        "created_at": now_iso(),
        "source_audio": str(Path(args.audio).resolve()),
        "audio_path": str(wav_path),
        "start_sec": start_sec,
        "end_sec": end_sec,
        "duration_sec": duration,
    }
    append_jsonl(segments_path, row)
    update_status(
        session_dir,
        state="queued",
        segments_total=len(segments) + 1,
        last_segment_id=next_id,
    )
    print(f"{session_dir} segment={next_id} start={start_sec:.3f} end={end_sec:.3f}")


def live_status(session_id: str) -> None:
    session_dir = live_session_dir(session_id)
    status_path = session_dir / "status.json"
    if not status_path.exists():
        raise SystemExit(f"ERROR: missing live status: {status_path}")
    print(json.dumps(read_json(status_path), ensure_ascii=False, indent=2))


def run_live(args) -> None:
    session_dir = live_session_dir(args.run_live)
    session_path = session_dir / "session.json"
    if not session_path.exists():
        raise SystemExit(f"ERROR: missing live session: {session_dir}")
    session = read_json(session_path)
    require_model_dir(session["model"], "model")
    require_file(session["mel"], "mel")
    prompt_ids = tokenize_user_prompt(session["model"], session.get("prompt", ""))

    transcript_tsv = session_dir / "transcript.tsv"
    output_path = Path(session.get("output") or (OUTPUT_DIR / f"{session_dir.name}_{session.get('subtitle_mode', 'sentence')}.srt"))
    batch_size = args.live_batch_size or int(session.get("batch_size", 128))
    subtitle_mode = session.get("subtitle_mode", "sentence")
    logger = TaskLogger(session_dir / "logs" / "orchestrator.log", quiet=args.quiet)
    infer = None
    infer_stderr = None
    total_infer_ms = 0.0
    total_output_tokens = 0

    try:
        while True:
            segments = read_jsonl(session_dir / "segments.jsonl")
            rows = read_live_transcript_rows(transcript_tsv)
            done_ids = {int(row["segment_id"]) for row in rows if row.get("segment_id")}
            pending = [seg for seg in segments if int(seg["segment_id"]) not in done_ids]

            if not pending:
                update_status(
                    session_dir,
                    state="idle",
                    segments_total=len(segments),
                    segments_done=len(done_ids),
                    output=str(output_path),
                )
                if not args.watch:
                    logger.log("[live] no pending segments")
                    return
                time.sleep(args.poll_sec)
                continue

            if infer is None:
                infer_stderr = open(session_dir / "logs" / "infer.stderr.log", "a", encoding="utf-8")
                infer = InferDaemon(session["model"], session["mel"], stderr=infer_stderr)

            update_status(session_dir, state="running", phase="asr", segments_total=len(segments), segments_done=len(done_ids))
            logger.log(f"[live] processing {len(pending)} pending segments")

            for start in range(0, len(pending), batch_size):
                batch = pending[start:start + batch_size]
                paths = [seg["audio_path"] for seg in batch]
                results, infer_ms, output_tokens = infer.transcribe_batch(paths, prompt_ids=prompt_ids)
                total_infer_ms += infer_ms
                total_output_tokens += output_tokens

                out_rows = []
                for seg in batch:
                    out_rows.append({
                        "segment_id": int(seg["segment_id"]),
                        "start_sec": float(seg["start_sec"]),
                        "end_sec": float(seg["end_sec"]),
                        "duration_sec": float(seg["duration_sec"]),
                        "audio_path": seg["audio_path"],
                        "text": results.get(seg["audio_path"], ""),
                    })
                append_live_transcripts(transcript_tsv, out_rows)

                rows = read_live_transcript_rows(transcript_tsv)
                write_live_srt(rows, output_path, subtitle_mode)
                done_count = len(rows)
                logger.log(
                    f"[live] done {done_count}/{len(segments)} segments, "
                    f"infer={infer_ms / 1000.0:.2f}s, tokens={output_tokens}"
                )
                update_status(
                    session_dir,
                    state="running",
                    phase="asr",
                    segments_total=len(segments),
                    segments_done=done_count,
                    asr_infer_sec=total_infer_ms / 1000.0,
                    output_tokens=total_output_tokens,
                    transcript_tsv=str(transcript_tsv),
                    output=str(output_path),
                )

            update_status(
                session_dir,
                state="idle" if args.watch else "completed",
                phase="idle" if args.watch else "done",
                segments_total=len(read_jsonl(session_dir / "segments.jsonl")),
                segments_done=len(read_live_transcript_rows(transcript_tsv)),
                asr_infer_sec=total_infer_ms / 1000.0,
                output_tokens=total_output_tokens,
                transcript_tsv=str(transcript_tsv),
                output=str(output_path),
            )
            if not args.watch:
                logger.log(f"[live] wrote {output_path}")
                return
    finally:
        if infer is not None:
            infer.close()
        if infer_stderr is not None:
            infer_stderr.close()
        logger.close()



def absolutize_runtime_args(args) -> None:
    for name in ("audio", "model", "mel", "fa_model", "output"):
        value = getattr(args, name, None)
        if value:
            setattr(args, name, str(Path(value).expanduser().resolve()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Long-audio ASR + forced alignment")
    parser.add_argument("--audio", help="Input audio file")
    parser.add_argument("--model", help="GLM-ASR model directory")
    parser.add_argument("--mel", help="Mel filterbank path")
    parser.add_argument("--fa-model", dest="fa_model", help="ForceAligner model directory")
    parser.add_argument("--lang", default="English", help="Alignment language")
    parser.add_argument("--output", default=None, help="Output SRT path")
    parser.add_argument("--batch-size", type=int, default=128, help="Infer-engine batch size")
    parser.add_argument("--segment-sec", type=float, default=SEGMENT_SEC, help="Chunk duration")
    parser.add_argument("--overlap-sec", type=float, default=OVERLAP_SEC, help="Chunk overlap")
    parser.add_argument("--subtitle-mode", choices=["word", "sentence"], default="word",
                        help="SRT granularity: sentence cues or word-level cues")
    parser.add_argument("--prompt", default="", help="Optional user prompt / hotwords text for ASR")
    parser.add_argument("--prompt-file", default=None, help="Read optional user prompt / hotwords from UTF-8 text file")
    parser.add_argument("--asr-only", action="store_true", help="Only run ASR and write transcript TSV")
    parser.add_argument("--reuse-asr", action="store_true", help="Reuse existing transcript TSV if present")
    parser.add_argument("--submit", action="store_true", help="Create a queued task and exit")
    parser.add_argument("--task-id", default=None, help="Task id for --submit")
    parser.add_argument("--run-task", default=None, help="Run a task directory or task id")
    parser.add_argument("--run-queue", action="store_true", help="Run queued tasks under dir/tasks")
    parser.add_argument("--status", default=None, help="Print task status by task directory or task id")
    parser.add_argument("--once", action="store_true", help="With --run-queue, run one task and exit")
    parser.add_argument("--asr-window-chunks", type=int, default=ASR_WINDOW_CHUNKS,
                        help="Max chunks to process before re-scanning queued tasks")
    parser.add_argument("--live-create", default=None, metavar="SESSION_ID",
                        help="Create a live ASR session for appended VAD chunks")
    parser.add_argument("--live-append", default=None, metavar="SESSION_ID",
                        help="Append one audio chunk to a live session")
    parser.add_argument("--run-live", default=None, metavar="SESSION_ID",
                        help="Transcribe pending chunks in a live session")
    parser.add_argument("--live-status", default=None, metavar="SESSION_ID",
                        help="Print live session status")
    parser.add_argument("--live-batch-size", type=int, default=None,
                        help="Batch size for --run-live; defaults to session batch size")
    parser.add_argument("--watch", action="store_true",
                        help="With --run-live, keep polling for appended chunks")
    parser.add_argument("--poll-sec", type=float, default=0.5,
                        help="Polling interval for --run-live --watch")
    parser.add_argument("--start-sec", type=float, default=None,
                        help="Timeline start for --live-append; defaults to previous segment end")
    parser.add_argument("--end-sec", type=float, default=None,
                        help="Timeline end for --live-append; defaults to start plus WAV duration")
    parser.add_argument("--quiet", action="store_true", help="Suppress high-level console progress")
    args = parser.parse_args()

    if args.status:
        print_task_status(args.status)
        return
    if args.live_status:
        live_status(args.live_status)
        return
    if args.live_create:
        if not args.model:
            raise SystemExit("ERROR: --model is required with --live-create")
        if not args.mel:
            raise SystemExit("ERROR: --mel is required with --live-create")
        absolutize_runtime_args(args)
        live_create(args)
        return
    if args.live_append:
        if not args.audio:
            raise SystemExit("ERROR: --audio is required with --live-append")
        live_append(args)
        return
    if args.run_live:
        run_live(args)
        return
    if args.run_task:
        run_task(resolve_task_dir(args.run_task))
        return
    if args.run_queue:
        run_queue(args.once, args.asr_window_chunks)
        return
    if not args.audio:
        raise SystemExit("ERROR: --audio is required unless --run-task or --run-queue is used")
    if not args.model:
        raise SystemExit("ERROR: --model is required")
    if not args.mel:
        raise SystemExit("ERROR: --mel is required")
    if not args.asr_only and not args.fa_model:
        raise SystemExit("ERROR: --fa-model is required unless --asr-only is used")
    absolutize_runtime_args(args)
    if args.submit:
        submit_task(args)
        return

    run_pipeline(args)


if __name__ == "__main__":
    main()
