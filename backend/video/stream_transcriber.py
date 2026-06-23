import json
import os
import queue
import re
import glob
import subprocess
import tempfile
import threading
import time
import uuid
import wave
import logging
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

import numpy as np

from video.asr_engine import asr_engine_daemon

logger = logging.getLogger("stream_translate")


# ---------------------------------------------------------------------------
# Fast single-step translation (used for live stream transcription)
# ---------------------------------------------------------------------------
_translate_lock = threading.Lock()
_translate_settings_cache: dict = {}
_translate_settings_ts: float = 0.0
_TRANSLATE_SETTINGS_TTL = 60.0  # refresh settings every 60 s


def _get_translate_client():
    """Return an LLM client configured from the translate settings."""
    global _translate_settings_cache, _translate_settings_ts
    now = time.time()
    with _translate_lock:
        if now - _translate_settings_ts > _TRANSLATE_SETTINGS_TTL:
            from video.views.set_setting import load_all_settings
            _translate_settings_cache = load_all_settings()
            _translate_settings_ts = now

    cfg = _translate_settings_cache
    default_cfg = cfg.get("DEFAULT", {})
    provider = (
        default_cfg.get("translate_selected_model_provider")
        or default_cfg.get("selected_model_provider")
        or "deepseek"
    )
    api_key = (
        default_cfg.get(f"translate_{provider}_api_key", "").strip()
        or default_cfg.get(f"{provider}_api_key", "").strip()
    )
    base_url = (
        default_cfg.get(f"translate_{provider}_base_url", "").strip()
        or default_cfg.get(f"{provider}_base_url", "").strip()
    )
    model = (
        default_cfg.get(f"translate_{provider}_model", "").strip()
        or default_cfg.get(f"{provider}_model", "").strip()
    )
    use_proxy = default_cfg.get("translate_use_proxy", "false").lower() == "true"
    proxy_url = (
        default_cfg.get("proxy_url", "")
        or cfg.get("Media Credentials", {}).get("proxy_url", "")
    )

    from utils.llm_client import PROVIDER_DEFAULTS
    defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["local"])
    if not base_url:
        base_url = defaults["url"]
    if not model:
        model = defaults["default_model"]

    if not api_key and provider not in {"local", "ollama", "lmstudio"}:
        logger.warning(
            "Realtime translation disabled: API key missing for provider=%s",
            provider,
        )
        return None, None
    if not base_url or not model:
        logger.warning(
            "Realtime translation disabled: incomplete provider config provider=%s base_url=%s model=%s",
            provider,
            bool(base_url),
            bool(model),
        )
        return None, None

    from utils.llm_client import ClientPool
    client = ClientPool.get_client(
        provider=provider if provider in PROVIDER_DEFAULTS else "local",
        api_key=api_key,
        base_url=base_url,
        use_proxy=use_proxy,
        proxy_url=proxy_url,
    )
    return client, model


def translate_segment(text: str, source_lang: str = "en", target_lang: str = "zh") -> str | None:
    """
    Fast single-step direct translation. Returns translated text or None on failure.
    Designed for low latency in live-stream scenarios.
    """
    if not text or not text.strip():
        return None

    source_lang = _normalize_lang_code(source_lang) or "auto"
    target_lang = _normalize_lang_code(target_lang)
    if not target_lang or source_lang == target_lang:
        return None

    lang_names = {"en": "English", "zh": "Simplified Chinese", "jp": "Japanese"}
    tgt = lang_names.get(target_lang, target_lang)
    if source_lang == "auto":
        prompt = (
            f"Translate the following text to {tgt}. "
            f"Output ONLY the translation, nothing else.\n\n{text}"
        )
    else:
        src = lang_names.get(source_lang, source_lang)
        prompt = (
            f"Translate the following {src} text to {tgt}. "
            f"Output ONLY the translation, nothing else.\n\n{text}"
        )

    try:
        client, model = _get_translate_client()
        if client is None or model is None:
            return None
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=512,
        )
        result = response.choices[0].message.content
        return result.strip() if result else None
    except Exception as exc:
        logger.warning("translate_segment failed: %s", exc)
        return None


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _normalize_lang_code(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"", "auto", "unknown", "und"}:
        return "auto" if normalized == "auto" else ""
    if normalized in {"zh", "zh-cn", "zh_hans", "cmn", "chi", "zho", "cn"}:
        return "zh"
    if normalized in {"en", "eng"}:
        return "en"
    if normalized in {"ja", "jp", "jpn"}:
        return "jp"
    return normalized


def _url_summary(url: str) -> str:
    if not url:
        return "empty"
    if os.path.exists(url):
        try:
            return f"file:{url} size={os.path.getsize(url)}"
        except OSError:
            return f"file:{url}"
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path[:80]}"
    return url[:120]


def _fmt_seconds(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.1f}s"


PCM_CHUNK_BYTES = 1024
SAMPLE_RATE = 16000
MAX_SEGMENT_SECONDS = 15.0
MAX_SEGMENT_SAMPLES = int(SAMPLE_RATE * MAX_SEGMENT_SECONDS)
OVERLAP_SECONDS = 0.5
OVERLAP_SAMPLES = int(SAMPLE_RATE * OVERLAP_SECONDS)
MIN_VAD_CHUNK_BYTES = PCM_CHUNK_BYTES
MIN_SEGMENT_SECONDS = _env_float("VIDGO_STREAM_ASR_MIN_SEGMENT_SECONDS", 0.7)
MIN_SEGMENT_SAMPLES = int(SAMPLE_RATE * MIN_SEGMENT_SECONDS)
MIN_SEGMENT_RMS = _env_float("VIDGO_STREAM_ASR_MIN_RMS", 80.0)
VAD_MIN_SILENCE_MS = 300
DEFAULT_BROWSER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
LIVE_ASR_BATCH_SIZE = 32
LIVE_ASR_BATCH_WAIT_SEC = 0.08
ASR_HALLUCINATION_MARKERS = (
    "please provide the speech",
    "provide the speech you would like me to transcribe",
    "i am unable to transcribe speech",
    "unable to transcribe speech into written format",
    "of course, i can help with that",
    "certainly! please provide",
    "sure, i can help with that",
)

_transcription_tasks = {}
_transcription_status = {}
_transcription_events = {}
_transcription_lock = threading.RLock()


@dataclass
class LiveASRItem:
    audio_path: str
    start_sample: int
    end_sample: int
    cancel_event: threading.Event
    on_result: Callable[["LiveASRItem", str, Exception | None], None]


class LiveASRBatcher:
    def __init__(
        self,
        max_batch: int = LIVE_ASR_BATCH_SIZE,
        max_wait_sec: float = LIVE_ASR_BATCH_WAIT_SEC,
    ):
        self.max_batch = max(1, max_batch)
        self.max_wait_sec = max(0.0, max_wait_sec)
        self._queue: queue.Queue[LiveASRItem] = queue.Queue()
        self._lock = threading.Lock()
        self._thread = None

    def submit(self, item: LiveASRItem) -> None:
        self._ensure_started()
        self._queue.put(item)

    def _ensure_started(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
                name="vidgo-live-asr-batcher",
            )
            self._thread.start()

    def _run(self) -> None:
        while True:
            first = self._queue.get()
            batch = [first]
            deadline = time.monotonic() + self.max_wait_sec
            while len(batch) < self.max_batch:
                timeout = deadline - time.monotonic()
                if timeout <= 0:
                    break
                try:
                    batch.append(self._queue.get(timeout=timeout))
                except queue.Empty:
                    break
            self._process_batch(batch)

    def _process_batch(self, batch: list[LiveASRItem]) -> None:
        live_items = [item for item in batch if not item.cancel_event.is_set()]
        for item in batch:
            if item.cancel_event.is_set():
                item.on_result(item, "", None)
        if not live_items:
            return

        try:
            texts = asr_engine_daemon.transcribe([item.audio_path for item in live_items])
        except Exception as exc:
            for item in live_items:
                item.on_result(item, "", exc)
            return

        for idx, item in enumerate(live_items):
            text = texts[idx] if idx < len(texts) else ""
            item.on_result(item, text or "", None)


live_asr_batcher = LiveASRBatcher()


def _is_bad_asr_text(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    if any(marker in normalized for marker in ASR_HALLUCINATION_MARKERS):
        return True

    compact = re.sub(r"[\s，。,.!?！？、；;：:]+", "", text)
    if len(compact) < 80:
        return False
    max_unit = min(18, len(compact) // 4)
    for unit_len in range(4, max_unit + 1):
        for offset in range(unit_len):
            pos = offset
            while pos + unit_len * 5 <= len(compact):
                unit = compact[pos:pos + unit_len]
                repeats = 1
                next_pos = pos + unit_len
                while (
                    next_pos + unit_len <= len(compact)
                    and compact[next_pos:next_pos + unit_len] == unit
                ):
                    repeats += 1
                    next_pos += unit_len
                if repeats >= 5 and repeats * unit_len >= min(60, len(compact) * 0.5):
                    return True
                pos = max(next_pos, pos + unit_len)
    return False


def _should_use_browser_user_agent(target_url: str, current_user_agent: str = "") -> bool:
    host = (urlparse(target_url).hostname or "").lower()
    if not (
        host.endswith("bilivideo.com")
        or host.endswith("bilibili.com")
        or host.endswith("hdslb.com")
    ):
        return False
    normalized = (current_user_agent or "").lower()
    return (
        not normalized
        or normalized.startswith("lavf/")
        or normalized.startswith("python-requests/")
        or normalized.startswith("ffmpeg/")
    )


def _build_http_input_args(target_url: str, headers: dict | None) -> list[str]:
    headers = headers or {}
    referer = headers.get("Referer") or headers.get("referer")
    user_agent = headers.get("User-Agent") or headers.get("user-agent")

    if _should_use_browser_user_agent(target_url, user_agent):
        user_agent = DEFAULT_BROWSER_USER_AGENT

    extra_header_lines = []
    for key, value in headers.items():
        if not value:
            continue
        lower_key = key.lower()
        if lower_key in {"referer", "user-agent"}:
            continue
        extra_header_lines.append(f"{key}: {value}")

    args: list[str] = []
    if referer:
        args += ["-referer", referer]
    if user_agent:
        args += ["-user_agent", user_agent]
    if extra_header_lines:
        args += ["-headers", "".join(f"{line}\r\n" for line in extra_header_lines)]
    return args


def _new_status(task_id: str, audio_url: str) -> dict:
    return {
        "task_id": task_id,
        "audio_url": audio_url,
        "status": "Queued",
        "segments": [],
        "progress": {"percent": 0.0},
        "error": None,
        "started_at": time.time(),
        "finished_at": None,
    }


def _emit_event(task_id: str, event_type: str, payload: dict) -> None:
    with _transcription_lock:
        event_queue = _transcription_events.get(task_id)
    if event_queue is not None:
        event_queue.put((event_type, payload))


def _set_status(task_id: str, **updates) -> dict | None:
    with _transcription_lock:
        status = _transcription_status.get(task_id)
        if status is None:
            return None
        status.update(updates)
        return dict(status)


def _update_progress(task_id: str, percent: float) -> None:
    clamped = round(max(0.0, min(100.0, percent)), 1)
    with _transcription_lock:
        status = _transcription_status.get(task_id)
        if status is None:
            return
        status["progress"] = {"percent": clamped}
    _emit_event(task_id, "progress", {"status": "running", "percent": clamped})


def _append_segment(task_id: str, segment: dict) -> None:
    with _transcription_lock:
        status = _transcription_status.get(task_id)
        if status is None:
            return
        status["segments"].append(segment)
    payload = dict(segment)
    payload["status"] = "running"
    _emit_event(task_id, "segment", payload)


def _mark_done(task_id: str) -> None:
    with _transcription_lock:
        status = _transcription_status.get(task_id)
        if status is None:
            return
        status["status"] = "Completed"
        status["finished_at"] = time.time()
        total_segments = len(status["segments"])
        _transcription_tasks.pop(task_id, None)
    _emit_event(
        task_id,
        "complete",
        {"status": "completed", "total_segments": total_segments},
    )


def _mark_cancelled(task_id: str) -> None:
    with _transcription_lock:
        status = _transcription_status.get(task_id)
        if status is None:
            return
        status["status"] = "Cancelled"
        status["error"] = None
        status["finished_at"] = time.time()
        total_segments = len(status["segments"])
        _transcription_tasks.pop(task_id, None)
    _emit_event(
        task_id,
        "end",
        {"status": "cancelled", "total_segments": total_segments},
    )


def _mark_error(task_id: str, message: str) -> None:
    with _transcription_lock:
        status = _transcription_status.get(task_id)
        if status is None:
            return
        status["status"] = "Failed"
        status["error"] = message
        status["finished_at"] = time.time()
        _transcription_tasks.pop(task_id, None)
    _emit_event(task_id, "error", {"status": "failed", "message": message})


class StreamTranscriber:
    def __init__(
        self,
        audio_url,
        proxy_url,
        headers,
        on_segment,
        on_progress,
        on_done,
        on_error,
        temp_audio_file=None,
        expected_duration=None,
        task_id="",
    ):
        self.task_id = task_id or "-"
        self.audio_url = audio_url
        self.proxy_url = proxy_url
        self.headers = headers or {}
        self.on_segment = on_segment
        self.on_progress = on_progress
        self.on_done = on_done
        self.on_error = on_error
        self.cancel_event = threading.Event()
        self._temp_audio_file = temp_audio_file
        self._expected_duration = expected_duration if expected_duration and expected_duration > 0 else None
        self._ffmpeg_proc = None
        self._sample_index = 0
        self._speech_chunks = []
        self._speech_start_sample = None
        self._speech_last_sample = None
        self._segment_index = 0
        self._total_audio_seconds = None
        self._tmp_dir = tempfile.mkdtemp(prefix="vidgo_stream_asr_")
        self._pcm_byte_buffer = bytearray()
        self._pending_asr = 0
        self._pending_asr_cond = threading.Condition()
        self._asr_error = None
        self._submitted_segments = 0
        self._emitted_segments = 0
        self._skipped_short_segments = 0
        self._skipped_low_rms_segments = 0
        self._empty_asr_results = 0
        self._filtered_asr_results = 0
        self._last_read_log_sample = 0
        self._ffmpeg_stderr_tail = ""

    def cancel(self) -> None:
        self.cancel_event.set()
        proc = self._ffmpeg_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    def run(self) -> None:
        try:
            self._run_pipeline()
            self._wait_for_pending_asr()
            if self._asr_error is not None:
                raise self._asr_error
            if not self.cancel_event.is_set():
                self.on_progress(100.0)
                self.on_done()
        except Exception as exc:
            logger.warning("[stream-asr:%s] failed: %s", self.task_id, exc)
            self.on_error(str(exc))
        finally:
            self._log_summary("finished")
            self._cleanup()

    def _run_pipeline(self) -> None:
        vad = self._create_vad_iterator()
        self._total_audio_seconds = self._probe_duration_seconds()
        logger.info(
            "[stream-asr:%s] start input=%s expected=%s probed=%s temp_audio=%s proxy=%s headers=%s",
            self.task_id,
            _url_summary(self.audio_url),
            _fmt_seconds(self._expected_duration),
            _fmt_seconds(self._total_audio_seconds),
            bool(self._temp_audio_file),
            bool(self.proxy_url),
            sorted(self.headers.keys()),
        )
        self.on_progress(0.0)
        cmd = ["ffmpeg"]
        cmd += _build_http_input_args(self.audio_url, self.headers)
        if self.proxy_url:
            cmd += ["-http_proxy", self.proxy_url]
        cmd += [
            "-i",
            self.audio_url,
            "-f",
            "s16le",
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            "1",
            "pipe:1",
        ]
        self._ffmpeg_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if self._ffmpeg_proc.stdout is None:
            raise RuntimeError("ffmpeg stdout is unavailable")
        while not self.cancel_event.is_set():
            chunk_bytes = self._ffmpeg_proc.stdout.read(PCM_CHUNK_BYTES)
            if not chunk_bytes:
                break
            self._pcm_byte_buffer.extend(chunk_bytes)
            self._drain_vad_buffer(vad)
        if self._pcm_byte_buffer:
            padded = bytes(self._pcm_byte_buffer)
            if len(padded) < MIN_VAD_CHUNK_BYTES:
                padded = padded + b"\x00" * (MIN_VAD_CHUNK_BYTES - len(padded))
            self._process_chunk(vad, padded)
            self._pcm_byte_buffer.clear()
        self._flush_pending_segment()
        if self._ffmpeg_proc.poll() is None:
            try:
                self._ffmpeg_proc.wait(timeout=5)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("ffmpeg did not exit after stdout closed") from exc
        self._capture_ffmpeg_stderr_tail()
        self._log_summary("ffmpeg-eof")
        if not self.cancel_event.is_set() and self._ffmpeg_proc.returncode not in (
            0,
            None,
        ):
            raise RuntimeError(
                f"ffmpeg exited with code {self._ffmpeg_proc.returncode}: {self._ffmpeg_stderr_tail.strip()}"
            )
        self._raise_if_audio_ended_early()

    def _process_chunk(self, vad, chunk_bytes: bytes) -> None:
        pcm_int16 = np.frombuffer(chunk_bytes, dtype=np.int16)
        if pcm_int16.size == 0:
            return
        chunk_start = self._sample_index
        chunk_end = self._sample_index + pcm_int16.size
        if self._speech_start_sample is not None:
            self._speech_chunks.append(pcm_int16.copy())
            self._speech_last_sample = chunk_end
            speech_duration_samples = chunk_end - self._speech_start_sample
            if speech_duration_samples >= MAX_SEGMENT_SAMPLES:
                self._force_split_speech()
                self._sample_index = chunk_end
                self._report_progress(chunk_end)
                return
        speech_dict = vad(pcm_int16.astype(np.float32) / 32768.0)
        if speech_dict and "start" in speech_dict:
            start_sample = int(speech_dict["start"])
            relative_start = max(0, start_sample - chunk_start)
            self._speech_start_sample = start_sample
            self._speech_last_sample = chunk_end
            self._speech_chunks = []
            self._speech_chunks.append(pcm_int16[relative_start:].copy())
        if (
            speech_dict
            and "end" in speech_dict
            and self._speech_start_sample is not None
        ):
            end_sample = int(speech_dict["end"])
            self._speech_last_sample = end_sample
            trimmed = self._trim_speech_chunks(end_sample)
            self._finalize_speech(trimmed, self._speech_start_sample, end_sample)
            self._speech_chunks = []
            self._speech_start_sample = None
            self._speech_last_sample = None
        self._sample_index = chunk_end
        self._report_progress(chunk_end)

    def _force_split_speech(self) -> None:
        if self._speech_start_sample is None or not self._speech_chunks:
            return
        pcm = np.concatenate(self._speech_chunks)
        base = self._speech_start_sample
        cursor = 0
        while cursor < pcm.size:
            chunk_end = min(pcm.size, cursor + MAX_SEGMENT_SAMPLES)
            self._finalize_speech(
                pcm[cursor:chunk_end], base + cursor, base + chunk_end
            )
            if chunk_end >= pcm.size:
                break
            cursor = chunk_end - OVERLAP_SAMPLES
        self._speech_chunks = []
        self._speech_start_sample = None
        self._speech_last_sample = None

    def _drain_vad_buffer(self, vad) -> None:
        while len(self._pcm_byte_buffer) >= MIN_VAD_CHUNK_BYTES:
            chunk = bytes(self._pcm_byte_buffer[:MIN_VAD_CHUNK_BYTES])
            del self._pcm_byte_buffer[:MIN_VAD_CHUNK_BYTES]
            self._process_chunk(vad, chunk)

    def _trim_speech_chunks(self, end_sample: int) -> np.ndarray:
        if not self._speech_chunks:
            return np.zeros((0,), dtype=np.int16)
        pcm = np.concatenate(self._speech_chunks)
        expected = max(0, end_sample - self._speech_start_sample)
        if expected and pcm.size > expected:
            pcm = pcm[:expected]
        return pcm

    def _flush_pending_segment(self) -> None:
        if self._speech_start_sample is None or not self._speech_chunks:
            return
        pcm = np.concatenate(self._speech_chunks)
        end_sample = self._speech_last_sample or (self._speech_start_sample + pcm.size)
        self._finalize_speech(pcm, self._speech_start_sample, end_sample)
        self._speech_chunks = []
        self._speech_start_sample = None
        self._speech_last_sample = None

    def _finalize_speech(
        self, pcm_int16: np.ndarray, start_sample: int, end_sample: int
    ) -> None:
        if (
            self.cancel_event.is_set()
            or pcm_int16.size == 0
            or end_sample <= start_sample
        ):
            return
        duration_sec = pcm_int16.size / SAMPLE_RATE
        samples = pcm_int16.astype(np.float32)
        rms = float(np.sqrt(np.mean(samples * samples)))
        if pcm_int16.size < MIN_SEGMENT_SAMPLES:
            self._skipped_short_segments += 1
            logger.info(
                "[stream-asr:%s] skip short segment start=%.3fs end=%.3fs duration=%.3fs rms=%.1f",
                self.task_id,
                start_sample / SAMPLE_RATE,
                end_sample / SAMPLE_RATE,
                duration_sec,
                rms,
            )
            return
        if rms < MIN_SEGMENT_RMS:
            self._skipped_low_rms_segments += 1
            logger.info(
                "[stream-asr:%s] skip low-rms segment start=%.3fs end=%.3fs duration=%.3fs rms=%.1f",
                self.task_id,
                start_sample / SAMPLE_RATE,
                end_sample / SAMPLE_RATE,
                duration_sec,
                rms,
            )
            return
        audio_path = os.path.join(self._tmp_dir, f"{uuid.uuid4().hex}.wav")
        self._write_wav_segment(audio_path, pcm_int16)
        self._submitted_segments += 1
        logger.info(
            "[stream-asr:%s] submit segment #%d start=%.3fs end=%.3fs duration=%.3fs rms=%.1f path=%s",
            self.task_id,
            self._submitted_segments,
            start_sample / SAMPLE_RATE,
            end_sample / SAMPLE_RATE,
            duration_sec,
            rms,
            os.path.basename(audio_path),
        )
        with self._pending_asr_cond:
            self._pending_asr += 1
        live_asr_batcher.submit(
            LiveASRItem(
                audio_path=audio_path,
                start_sample=start_sample,
                end_sample=end_sample,
                cancel_event=self.cancel_event,
                on_result=self._on_asr_result,
            )
        )

    def _write_wav_segment(self, path: str, pcm_int16: np.ndarray) -> None:
        pcm = np.asarray(pcm_int16, dtype=np.int16)
        with wave.open(path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(pcm.tobytes())

    def _on_asr_result(self, item: LiveASRItem, text: str, error: Exception | None) -> None:
        try:
            if error is not None:
                logger.warning(
                    "[stream-asr:%s] asr error for start=%.3fs end=%.3fs: %s",
                    self.task_id,
                    item.start_sample / SAMPLE_RATE,
                    item.end_sample / SAMPLE_RATE,
                    error,
                )
                self._asr_error = error
                return
            if self.cancel_event.is_set():
                return
            text = text.strip() if text else ""
            if not text:
                self._empty_asr_results += 1
                logger.info(
                    "[stream-asr:%s] drop empty ASR result start=%.3fs end=%.3fs",
                    self.task_id,
                    item.start_sample / SAMPLE_RATE,
                    item.end_sample / SAMPLE_RATE,
                )
                return
            if _is_bad_asr_text(text):
                self._filtered_asr_results += 1
                logger.warning(
                    "[stream-asr:%s] drop hallucinated ASR result start=%.3fs end=%.3fs text=%r",
                    self.task_id,
                    item.start_sample / SAMPLE_RATE,
                    item.end_sample / SAMPLE_RATE,
                    text[:160],
                )
                return
            segment = {
                "index": self._segment_index,
                "text": text,
                "start": round(item.start_sample / SAMPLE_RATE, 3),
                "end": round(item.end_sample / SAMPLE_RATE, 3),
            }
            self._segment_index += 1
            self._emitted_segments += 1
            logger.info(
                "[stream-asr:%s] emit segment #%d start=%.3fs end=%.3fs chars=%d",
                self.task_id,
                self._emitted_segments,
                item.start_sample / SAMPLE_RATE,
                item.end_sample / SAMPLE_RATE,
                len(text),
            )
            self.on_segment(segment)
        finally:
            try:
                os.remove(item.audio_path)
            except FileNotFoundError:
                pass
            with self._pending_asr_cond:
                self._pending_asr -= 1
                self._pending_asr_cond.notify_all()

    def _wait_for_pending_asr(self) -> None:
        with self._pending_asr_cond:
            while self._pending_asr > 0:
                self._pending_asr_cond.wait(timeout=0.5)

    def _report_progress(self, processed_samples: int) -> None:
        duration = self._expected_duration or self._total_audio_seconds
        if not duration or duration <= 0:
            return
        processed_seconds = processed_samples / SAMPLE_RATE
        if processed_samples - self._last_read_log_sample >= SAMPLE_RATE * 60:
            self._last_read_log_sample = processed_samples
            logger.info(
                "[stream-asr:%s] read progress %.1fs/%s submitted=%d emitted=%d skipped_short=%d skipped_low_rms=%d",
                self.task_id,
                processed_seconds,
                _fmt_seconds(duration),
                self._submitted_segments,
                self._emitted_segments,
                self._skipped_short_segments,
                self._skipped_low_rms_segments,
            )
        self.on_progress(min(99.0, processed_seconds / duration * 100.0))

    def _raise_if_audio_ended_early(self) -> None:
        if not self._expected_duration or self._expected_duration <= 0:
            return
        processed_seconds = self._sample_index / SAMPLE_RATE
        missing_seconds = self._expected_duration - processed_seconds
        if missing_seconds <= 30:
            return
        if processed_seconds >= self._expected_duration * 0.85:
            return
        logger.warning(
            "[stream-asr:%s] early EOF detected read=%s expected=%s probed=%s stderr_tail=%r",
            self.task_id,
            _fmt_seconds(processed_seconds),
            _fmt_seconds(self._expected_duration),
            _fmt_seconds(self._total_audio_seconds),
            self._ffmpeg_stderr_tail[-1000:],
        )
        raise RuntimeError(
            "Audio stream ended early: "
            f"read {processed_seconds:.1f}s of expected {self._expected_duration:.1f}s. "
            "Please resolve the stream again or use the normal download/subtitle generation path."
        )

    def _capture_ffmpeg_stderr_tail(self) -> None:
        proc = self._ffmpeg_proc
        if proc is None or proc.stderr is None:
            return
        try:
            stderr = proc.stderr.read()
        except Exception:
            return
        if not stderr:
            return
        text = stderr.decode("utf-8", errors="ignore")
        self._ffmpeg_stderr_tail = text[-2000:]

    def _log_summary(self, phase: str) -> None:
        logger.info(
            "[stream-asr:%s] %s read=%s expected=%s probed=%s returncode=%s submitted=%d emitted=%d "
            "skipped_short=%d skipped_low_rms=%d empty_asr=%d filtered_asr=%d pending=%d stderr_tail=%r",
            self.task_id,
            phase,
            _fmt_seconds(self._sample_index / SAMPLE_RATE),
            _fmt_seconds(self._expected_duration),
            _fmt_seconds(self._total_audio_seconds),
            self._ffmpeg_proc.returncode if self._ffmpeg_proc is not None else None,
            self._submitted_segments,
            self._emitted_segments,
            self._skipped_short_segments,
            self._skipped_low_rms_segments,
            self._empty_asr_results,
            self._filtered_asr_results,
            self._pending_asr,
            self._ffmpeg_stderr_tail[-1000:],
        )

    def _probe_duration_seconds(self) -> float | None:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
        ]
        cmd += _build_http_input_args(self.audio_url, self.headers)
        if self.proxy_url:
            cmd += ["-http_proxy", self.proxy_url]
        cmd.append(self.audio_url)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return None
            payload = json.loads(result.stdout or "{}")
            duration = payload.get("format", {}).get("duration")
            return float(duration) if duration is not None else None
        except Exception:
            return None

    def _create_vad_iterator(self):
        backend = self._get_vad_backend().strip().lower()
        if backend in {"", "auto"}:
            backend = "silero_onnx"
        if backend in {"silero", "silero_onnx"}:
            try:
                return self._create_silero_onnx_vad()
            except Exception as exc:
                logger.warning(
                    "[stream-asr:%s] Silero ONNX VAD failed; falling back to FireRed ONNX VAD: %s",
                    self.task_id,
                    exc,
                )
                return self._create_firered_vad()
        if backend == "firered":
            return self._create_firered_vad()
        logger.warning(
            "[stream-asr:%s] unknown VAD backend %r; falling back to FireRed ONNX VAD",
            self.task_id,
            backend,
        )
        return self._create_firered_vad()

    def _get_vad_backend(self) -> str:
        try:
            from .views.set_setting import load_all_settings
            s = load_all_settings()
            return s.get("Transcription Engine", {}).get("vad_backend", "silero_onnx")
        except Exception:
            return "silero_onnx"

    def _create_silero_onnx_vad(self):
        from asr_utils.silero_vad_onnx import (
            SileroOnnxVAD,
            default_silero_onnx_path,
        )
        return SileroOnnxVAD(
            default_silero_onnx_path(),
            threshold=0.5,
            sampling_rate=SAMPLE_RATE,
            min_silence_duration_ms=VAD_MIN_SILENCE_MS,
        )

    def _create_firered_vad(self):
        from asr_utils.firered_vad import FireRedVAD
        model_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "third_party", "firered-vad", "firered_vad.int8.onnx",
        )
        return FireRedVAD(
            model_path,
            threshold=0.5,
            sampling_rate=SAMPLE_RATE,
            min_silence_duration_ms=VAD_MIN_SILENCE_MS,
        )

    def _cleanup(self) -> None:
        proc = self._ffmpeg_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if proc is not None and proc.stderr is not None:
            try:
                proc.stderr.close()
            except Exception:
                pass
        if proc is not None and proc.stdout is not None:
            try:
                proc.stdout.close()
            except Exception:
                pass
        try:
            os.rmdir(self._tmp_dir)
        except OSError:
            pass
        if self._temp_audio_file:
            try:
                os.remove(self._temp_audio_file)
            except OSError:
                pass


def _probe_file_duration_seconds(path: str) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return None
        payload = json.loads(result.stdout or "{}")
        duration = payload.get("format", {}).get("duration")
        return float(duration) if duration is not None else None
    except Exception:
        return None


def _downloaded_youtube_path(ydl, info: dict, tmp_base: str) -> str | None:
    for item in info.get("requested_downloads") or []:
        filepath = item.get("filepath")
        if filepath and os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            return filepath
    try:
        filepath = ydl.prepare_filename(info)
        if filepath and os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            return filepath
    except Exception:
        pass
    candidates = [
        path
        for path in glob.glob(tmp_base + ".*")
        if os.path.exists(path) and os.path.getsize(path) > 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (os.path.getmtime(path), os.path.getsize(path)))


def _prefetch_youtube_audio(
    audio_url: str,
    original_url: str,
    proxy_url: str | None,
    task_id: str,
    audio_format_id: str = "",
    expected_duration: float | None = None,
) -> str | None:
    """Download YouTube audio to temp file so ffmpeg reads locally, not via Django relay."""
    target_url = original_url or audio_url
    if 'youtube.com' not in target_url and 'youtu.be' not in target_url:
        return None
    try:
        import yt_dlp, uuid
        tmp_base = os.path.join(tempfile.gettempdir(), f"vidgo_yt_{uuid.uuid4().hex}")
        ydl_opts = {
            'format': audio_format_id or 'bestaudio/best',
            'outtmpl': tmp_base + '.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
        }
        if proxy_url:
            ydl_opts['proxy'] = proxy_url
        logger.info(
            "[stream-asr:%s] youtube prefetch start target=%s format=%s expected=%s proxy=%s",
            task_id,
            _url_summary(target_url),
            audio_format_id or "bestaudio/best",
            _fmt_seconds(expected_duration),
            bool(proxy_url),
        )
        with _transcription_lock:
            _transcription_status[task_id]["status"] = "Downloading"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target_url, download=True)
            downloaded_path = _downloaded_youtube_path(ydl, info or {}, tmp_base)
        if downloaded_path:
            duration = _probe_file_duration_seconds(downloaded_path)
            try:
                size = os.path.getsize(downloaded_path)
            except OSError:
                size = -1
            logger.info(
                "[stream-asr:%s] youtube prefetch done path=%s size=%d duration=%s expected=%s ext=%s format_id=%s",
                task_id,
                downloaded_path,
                size,
                _fmt_seconds(duration),
                _fmt_seconds(expected_duration),
                (info or {}).get("ext"),
                (info or {}).get("format_id"),
            )
            if (
                expected_duration
                and duration
                and expected_duration > 0
                and expected_duration - duration > 30
                and duration < expected_duration * 0.85
            ):
                logger.warning(
                    "yt-dlp audio prefetch ended early: path=%s duration=%.1fs expected=%.1fs",
                    downloaded_path,
                    duration,
                    expected_duration,
                )
                try:
                    os.remove(downloaded_path)
                except OSError:
                    pass
                return None
            return downloaded_path
        logger.warning(
            "[stream-asr:%s] youtube prefetch completed but downloaded file was not found target=%s tmp_base=%s",
            task_id,
            _url_summary(target_url),
            tmp_base,
        )
    except Exception as e:
        logger.warning("[stream-asr:%s] youtube prefetch failed: %s; falling back to direct ffmpeg", task_id, e)
    return None


def start_transcription(task_id, audio_url, proxy_url, headers,
                        source_lang="en", target_lang="", original_url="",
                        expected_duration=0.0, audio_format_id=""):
    with _transcription_lock:
        _transcription_status[task_id] = _new_status(task_id, audio_url)
        _transcription_events[task_id] = queue.Queue()

    expected_duration = expected_duration if expected_duration and expected_duration > 0 else None
    logger.info(
        "[stream-asr:%s] start_transcription audio=%s original=%s expected=%s audio_format_id=%s source_lang=%s target_lang=%s headers=%s proxy=%s",
        task_id,
        _url_summary(audio_url),
        _url_summary(original_url),
        _fmt_seconds(expected_duration),
        audio_format_id or "",
        source_lang,
        target_lang,
        sorted((headers or {}).keys()),
        bool(proxy_url),
    )
    local_audio = _prefetch_youtube_audio(
        audio_url,
        original_url,
        proxy_url,
        task_id,
        audio_format_id=audio_format_id,
        expected_duration=expected_duration,
    )

    source_lang = _normalize_lang_code(source_lang) or "auto"
    target_lang = _normalize_lang_code(target_lang)
    do_translate = bool(target_lang) and target_lang != source_lang

    def on_segment(segment):
        if do_translate:
            translated = translate_segment(segment["text"], source_lang, target_lang)
            if translated:
                segment["translation"] = translated
        _append_segment(task_id, segment)

    def on_progress(percent):
        _update_progress(task_id, percent)

    def on_done():
        _mark_done(task_id)

    def on_error(message):
        _mark_error(task_id, message)

    transcriber = StreamTranscriber(
        audio_url=local_audio or audio_url,
        proxy_url=proxy_url if not local_audio else None,
        headers=headers if not local_audio else {},
        on_segment=on_segment,
        on_progress=on_progress,
        on_done=on_done,
        on_error=on_error,
        temp_audio_file=local_audio,
        expected_duration=expected_duration,
        task_id=task_id,
    )
    thread = threading.Thread(
        target=transcriber.run, daemon=True, name=f"stream-transcriber-{task_id}"
    )
    with _transcription_lock:
        _transcription_tasks[task_id] = transcriber
        _transcription_status[task_id]["status"] = "Running"
    thread.start()
    return task_id


def cancel_transcription(task_id):
    with _transcription_lock:
        transcriber = _transcription_tasks.get(task_id)
    if transcriber is None:
        return False
    transcriber.cancel()
    _mark_cancelled(task_id)
    return True
