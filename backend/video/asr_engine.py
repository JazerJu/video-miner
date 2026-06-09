import os
import subprocess
import threading
from typing import List

from .views.set_setting import load_all_settings


_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ASR_UTILS = os.path.join(_BACKEND_DIR, "asr_utils", "glm-asr-stack")
_MODELS_DIR = os.path.join(_BACKEND_DIR, "models", "glm-asr")

DEFAULT_ENGINE_PATH = os.path.join(_ASR_UTILS, "Infer-engine", "glm_asr_infer")
DEFAULT_MODEL_DIR = os.environ.get(
    "GLM_ASR_MODEL_DIR",
    os.path.join(_MODELS_DIR, "glm-asr-nano-2512"),
)
DEFAULT_MEL_FILTERS = os.path.join(_ASR_UTILS, "resources", "mel_filters.bin")
DEFAULT_ENGINE_ENV = {
    "GLMASR_VRAM_UTIL": "0.9",
    "GLMASR_MAX_SEQS": "256",
    "GLMASR_ENCODER_FA_PIPELINED": "1",
    "GLMASR_ENCODER_FA_VLLM": "1",
    "GLMASR_ENCODER_FA_LONG_MIN_SEQ": "1",
    "GLMASR_ENCODER_FA_MIN_SEQ": "1",
}


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
        self._stderr_lines: list[str] = []
        self._stderr_thread = None

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
            env={**os.environ, **DEFAULT_ENGINE_ENV},
        )
        self._stderr_lines = []
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr_locked_proc,
            args=(self._proc,),
            daemon=True,
            name="glm-asr-stderr-drain",
        )
        self._stderr_thread.start()
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
            if line.startswith("INFER_TIME:") or line.startswith("OUTPUT_TOKENS:"):
                continue
            path, sep, text = line.partition(": ")
            if not sep:
                continue
            if path in outputs:
                outputs[path] = text
        return [outputs[path] for path in bin_paths]

    def _drain_stderr_locked_proc(self, proc) -> None:
        if proc.stderr is None:
            return
        for line in proc.stderr:
            line = line.rstrip("\r\n")
            if not line:
                continue
            self._stderr_lines.append(line)
            if len(self._stderr_lines) > 200:
                del self._stderr_lines[:100]

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
        stderr_text = "\n".join(self._stderr_lines[-30:])
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
