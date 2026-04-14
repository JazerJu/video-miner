import os
import subprocess
import threading
from typing import List

from video.views.set_setting import load_all_settings


DEFAULT_ENGINE_PATH = "/data/fwsr/glm-asr/Infer-engine/glm_asr_infer"
DEFAULT_MODEL_DIR = "/data/fwsr/glm-asr/GLM-ASR/glm-asr-nvfp4-awq"
DEFAULT_MEL_FILTERS = "/data/fwsr/glm-asr/output/mel_filters.bin"


def _get_engine_config() -> tuple[str, str, str]:
    settings = load_all_settings()
    engine_settings = settings.get("Transcription Engine", {})
    engine_path = (
        engine_settings.get("glm_asr_engine_path", "").strip() or DEFAULT_ENGINE_PATH
    )
    model_dir = (
        engine_settings.get("glm_asr_model_dir", "").strip() or DEFAULT_MODEL_DIR
    )
    mel_filters = (
        engine_settings.get("glm_asr_mel_filters", "").strip() or DEFAULT_MEL_FILTERS
    )
    return engine_path, model_dir, mel_filters


class ASREngineDaemon:
    def __init__(self):
        self._lock = threading.Lock()
        self._proc = None

    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        with self._lock:
            self._ensure_started_locked()

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def transcribe(self, bin_paths: List[str]) -> List[str]:
        if not bin_paths:
            return []
        with self._lock:
            self._ensure_started_locked()
            try:
                return self._transcribe_locked(bin_paths)
            except Exception:
                self._stop_locked()
                raise

    def _ensure_started_locked(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        self._stop_locked()
        engine_path, model_dir, mel_filters = _get_engine_config()
        if not os.path.exists(engine_path):
            raise FileNotFoundError(f"ASR engine binary not found: {engine_path}")
        if not os.path.exists(model_dir):
            raise FileNotFoundError(f"ASR model dir not found: {model_dir}")
        if not os.path.exists(mel_filters):
            raise FileNotFoundError(f"ASR mel filters not found: {mel_filters}")
        self._proc = subprocess.Popen(
            [engine_path, "--daemon"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._send_line_locked(f"LOAD {model_dir}")
        self._wait_ready_locked("after model load")
        self._send_line_locked(f"MEL {mel_filters}")
        self._wait_ready_locked("after mel filter load")

    def _transcribe_locked(self, bin_paths: List[str]) -> List[str]:
        self._send_line_locked(f"BATCH {len(bin_paths)}")
        for bin_path in bin_paths:
            self._send_line_locked(bin_path)
        self._send_line_locked("RUN")

        outputs = {path: "" for path in bin_paths}
        while True:
            line = self._read_stdout_line_locked()
            if line == "READY":
                break
            if line.startswith("INFER_TIME:"):
                continue
            path, sep, text = line.partition(": ")
            if not sep:
                continue
            if path in outputs:
                outputs[path] = text
        return [outputs[path] for path in bin_paths]

    def _send_line_locked(self, line: str) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("ASR engine stdin is unavailable")
        if self._proc.poll() is not None:
            raise RuntimeError(self._build_crash_error("process exited before write"))
        try:
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()
        except BrokenPipeError as exc:
            raise RuntimeError(self._build_crash_error("broken pipe")) from exc

    def _wait_ready_locked(self, stage: str) -> None:
        while True:
            line = self._read_stdout_line_locked()
            if line == "READY":
                return
            if line.startswith("INFER_TIME:"):
                continue
            raise RuntimeError(f"Unexpected ASR daemon response {stage}: {line}")

    def _read_stdout_line_locked(self) -> str:
        if self._proc is None or self._proc.stdout is None:
            raise RuntimeError("ASR engine stdout is unavailable")
        line = self._proc.stdout.readline()
        if line:
            return line.rstrip("\r\n")
        raise RuntimeError(self._build_crash_error("stdout closed"))

    def _build_crash_error(self, context: str) -> str:
        stderr_text = ""
        if self._proc is not None and self._proc.stderr is not None:
            try:
                stderr_text = self._proc.stderr.read().strip()
            except Exception:
                stderr_text = ""
        suffix = f": {stderr_text}" if stderr_text else ""
        return f"ASR daemon crashed ({context}){suffix}"

    def _stop_locked(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.poll() is None and proc.stdin is not None:
                proc.stdin.write("QUIT\n")
                proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


asr_engine_daemon = ASREngineDaemon()
