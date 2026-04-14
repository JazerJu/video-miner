import json
import os
import queue
import subprocess
import tempfile
import threading
import time
import uuid
from urllib.parse import urlparse

import numpy as np

from video.asr_engine import asr_engine_daemon


PCM_CHUNK_BYTES = 1024
SAMPLE_RATE = 16000
MAX_SEGMENT_SECONDS = 15.0
MAX_SEGMENT_SAMPLES = int(SAMPLE_RATE * MAX_SEGMENT_SECONDS)
OVERLAP_SECONDS = 0.5
OVERLAP_SAMPLES = int(SAMPLE_RATE * OVERLAP_SECONDS)
MIN_VAD_CHUNK_BYTES = PCM_CHUNK_BYTES
VAD_MIN_SILENCE_MS = 300
DEFAULT_BROWSER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

_transcription_tasks = {}
_transcription_status = {}
_transcription_events = {}
_transcription_lock = threading.RLock()


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
    ):
        self.audio_url = audio_url
        self.proxy_url = proxy_url
        self.headers = headers or {}
        self.on_segment = on_segment
        self.on_progress = on_progress
        self.on_done = on_done
        self.on_error = on_error
        self.cancel_event = threading.Event()
        self._ffmpeg_proc = None
        self._sample_index = 0
        self._speech_chunks = []
        self._speech_start_sample = None
        self._speech_last_sample = None
        self._segment_index = 0
        self._total_audio_seconds = None
        self._tmp_dir = tempfile.mkdtemp(prefix="vidgo_stream_asr_")
        self._pcm_byte_buffer = bytearray()

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
            if not self.cancel_event.is_set():
                self.on_progress(100.0)
                self.on_done()
        except Exception as exc:
            self.on_error(str(exc))
        finally:
            self._cleanup()

    def _run_pipeline(self) -> None:
        vad = self._create_vad_iterator()
        self._total_audio_seconds = self._probe_duration_seconds()
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
            self._ffmpeg_proc.wait(timeout=5)
        if not self.cancel_event.is_set() and self._ffmpeg_proc.returncode not in (
            0,
            None,
        ):
            stderr = b""
            if self._ffmpeg_proc.stderr is not None:
                stderr = self._ffmpeg_proc.stderr.read()
            raise RuntimeError(
                f"ffmpeg exited with code {self._ffmpeg_proc.returncode}: {stderr.decode('utf-8', errors='ignore').strip()}"
            )

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
        pcm_float = pcm_int16.astype(np.float32) / 32768.0
        bin_path = os.path.join(self._tmp_dir, f"{uuid.uuid4().hex}.bin")
        try:
            pcm_float.tofile(bin_path)
            texts = asr_engine_daemon.transcribe([bin_path])
            if self.cancel_event.is_set():
                return
            text = texts[0].strip() if texts and texts[0] and texts[0].strip() else ""
            if not text:
                return
            segment = {
                "index": self._segment_index,
                "text": text,
                "start": round(start_sample / SAMPLE_RATE, 3),
                "end": round(end_sample / SAMPLE_RATE, 3),
            }
            self._segment_index += 1
            self.on_segment(segment)
        finally:
            try:
                os.remove(bin_path)
            except FileNotFoundError:
                pass

    def _report_progress(self, processed_samples: int) -> None:
        if not self._total_audio_seconds or self._total_audio_seconds <= 0:
            return
        processed_seconds = processed_samples / SAMPLE_RATE
        self.on_progress(processed_seconds / self._total_audio_seconds * 100.0)

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
        import sys

        silero_src = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), "..", "third_party", "silero-vad", "src"
            )
        )
        if silero_src not in sys.path:
            sys.path.insert(0, silero_src)
        from silero_vad import VADIterator, load_silero_vad

        model = load_silero_vad(onnx=False)
        return VADIterator(
            model,
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


def start_transcription(task_id, audio_url, proxy_url, headers):
    with _transcription_lock:
        _transcription_status[task_id] = _new_status(task_id, audio_url)
        _transcription_events[task_id] = queue.Queue()

    def on_segment(segment):
        _append_segment(task_id, segment)

    def on_progress(percent):
        _update_progress(task_id, percent)

    def on_done():
        _mark_done(task_id)

    def on_error(message):
        _mark_error(task_id, message)

    transcriber = StreamTranscriber(
        audio_url=audio_url,
        proxy_url=proxy_url,
        headers=headers,
        on_segment=on_segment,
        on_progress=on_progress,
        on_done=on_done,
        on_error=on_error,
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
