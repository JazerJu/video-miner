"""
GLM-ASR Stack WSR adapter for VidGo.

Reuses VidGo's asr_engine_daemon for ASR inference (shared with streaming transcription),
then runs ForceAligner separately. Falls back to subprocess for non-VidGo environments.
"""

import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Callable, Optional

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ASR_UTILS = os.path.join(_BACKEND_DIR, "asr_utils", "glm-asr-stack")
_MODELS_DIR = os.path.join(_BACKEND_DIR, "models", "glm-asr")

_GLM_ASR_BIN = os.path.join(_ASR_UTILS, "bin", "glm-asr")
_DEFAULT_MODEL = os.path.join(_ASR_UTILS, "models", "glm-asr-bf16")
_DEFAULT_FA_MODEL = os.path.join(_ASR_UTILS, "models", "qwen3-forcealigner-0.6b")
_DEFAULT_MEL = os.path.join(_ASR_UTILS, "resources", "mel_filters.bin")

SAMPLE_RATE = 16000
SEGMENT_SEC = 30.0

LANGUAGE_MAP = {"zh": "Chinese", "en": "English", "ja": "Japanese"}


def _import_orchestrator_funcs():
    sys.path.insert(0, _ASR_UTILS)
    from bin.orchestrator import (
        decode_to_wav, split_wav, merge_to_srt, FADaemon, sec_to_srt,
    )
    return decode_to_wav, split_wav, merge_to_srt, FADaemon, sec_to_srt


def is_available() -> bool:
    if not os.path.isfile(_GLM_ASR_BIN):
        return False
    model_dir = os.environ.get("GLM_ASR_MODEL", _DEFAULT_MODEL)
    fa_model_dir = os.environ.get("GLM_ASR_FA_MODEL", _DEFAULT_FA_MODEL)
    return os.path.isdir(model_dir) and os.path.isdir(fa_model_dir)


def transcribe_audio(
    audio_file_path: str,
    progress_cb: Callable[[str], None],
    language: Optional[str] = None,
    subtitle_mode: str = "word",
) -> str:
    progress_cb("Running")

    try:
        from video.asr_engine import asr_engine_daemon
        return _transcribe_inprocess(audio_file_path, progress_cb, language, subtitle_mode, asr_engine_daemon)
    except ImportError:
        return _transcribe_subprocess(audio_file_path, progress_cb, language, subtitle_mode)


def _transcribe_inprocess(
    audio_file_path: str,
    progress_cb: Callable[[str], None],
    language: Optional[str],
    subtitle_mode: str,
    asr_engine_daemon,
) -> str:
    decode_to_wav, split_wav, merge_to_srt, FADaemon, sec_to_srt = _import_orchestrator_funcs()
    fa_model_dir = os.environ.get("GLM_ASR_FA_MODEL", _DEFAULT_FA_MODEL)
    lang = LANGUAGE_MAP.get(language, "Chinese")

    with tempfile.TemporaryDirectory(prefix="glm_asr_") as work_dir:
        work = Path(work_dir)
        audio_dir = work / "audio"
        chunk_dir = work / "chunks"

        # 1. Decode to 16k mono WAV
        wav_path = decode_to_wav(os.path.abspath(audio_file_path), audio_dir)
        progress_cb("ASR: Decoding audio")

        # 2. Split into 30s chunks
        segments = split_wav(wav_path, chunk_dir, SEGMENT_SEC, 0.0)
        if not segments:
            raise RuntimeError("Audio produced no chunks")
        progress_cb(f"ASR: {len(segments)} chunks")

        # 3. ASR via shared daemon
        texts = {}
        chunk_paths = [seg["path"] for seg in segments]
        batch_size = 32
        for start in range(0, len(chunk_paths), batch_size):
            batch = chunk_paths[start:start + batch_size]
            results = asr_engine_daemon.transcribe(batch)
            for path, text in zip(batch, results):
                texts[path] = text
            done = min(start + batch_size, len(chunk_paths))
            progress_cb(f"ASR: {done}/{len(chunk_paths)} chunks")

        # 4. Release ASR daemon GPU memory
        asr_engine_daemon.stop()
        progress_cb("ASR: Done, released GPU")

        # 5. ForceAligner
        fa = FADaemon(fa_model_dir)
        aligned_segments = []
        try:
            for seg in segments:
                text = texts.get(seg["path"], "")
                if not text or text == "[ERROR]":
                    continue
                words = fa.align_one(seg["path"], text, lang)
                aligned_segments.append({"start_sec": seg["start_sec"], "text": text, "words": words})
        finally:
            fa.close()
        progress_cb(f"Align: {len(aligned_segments)} segments")

        # 6. Build SRT
        srt_path = work / "output.srt"
        merge_to_srt(aligned_segments, srt_path, subtitle_mode)

        with open(srt_path, "r", encoding="utf-8") as f:
            srt_content = f.read()

        if not srt_content.strip():
            raise RuntimeError("GLM-ASR produced empty SRT")

        progress_cb("Completed")
        return srt_content


def _transcribe_subprocess(
    audio_file_path: str,
    progress_cb: Callable[[str], None],
    language: Optional[str],
    subtitle_mode: str,
) -> str:
    model_dir = os.environ.get("GLM_ASR_MODEL", _DEFAULT_MODEL)
    fa_model_dir = os.environ.get("GLM_ASR_FA_MODEL", _DEFAULT_FA_MODEL)

    audio_file_path = os.path.abspath(audio_file_path)

    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False, mode="w") as tmp:
        output_path = os.path.abspath(tmp.name)

    try:
        cmd = [
            _GLM_ASR_BIN, "transcribe",
            audio_file_path,
            "--subtitle-mode", subtitle_mode,
            "--output", output_path,
        ]

        env = {**os.environ, "GLM_ASR_MODEL": model_dir, "GLM_ASR_FA_MODEL": fa_model_dir}
        mel_path = os.environ.get("GLM_ASR_MEL", _DEFAULT_MEL)
        if os.path.isfile(mel_path):
            cmd.extend(["--mel", mel_path])

        lang = LANGUAGE_MAP.get(language)
        if lang:
            cmd.extend(["--lang", lang])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,
            cwd=_ASR_UTILS,
            env=env,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(f"glm-asr exited with code {result.returncode}: {stderr[:500]}")

        if not os.path.isfile(output_path):
            raise RuntimeError("glm-asr completed but produced no output SRT file")

        with open(output_path, "r", encoding="utf-8") as f:
            srt_content = f.read()

        if not srt_content.strip():
            raise RuntimeError("glm-asr produced empty SRT")

        progress_cb("Completed")
        return srt_content

    finally:
        if os.path.exists(output_path):
            os.unlink(output_path)
