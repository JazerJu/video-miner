"""
GLM-ASR Stack WSR adapter for VidGo.

Wraps `glm-asr transcribe` (ASR + ForceAligner pipeline) to produce
sentence-level SRT with word timestamps. Fits the TranscriptionEngine contract.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ASR_UTILS = os.path.join(_BACKEND_DIR, "asr_utils", "glm-asr-stack")
_MODELS_DIR = os.path.join(_BACKEND_DIR, "models", "glm-asr")

_GLM_ASR_BIN = os.path.join(_ASR_UTILS, "bin", "glm-asr")
_DEFAULT_MODEL = os.path.join(_ASR_UTILS, "models", "glm-asr-bf16")
_DEFAULT_FA_MODEL = os.path.join(_ASR_UTILS, "models", "qwen3-forcealigner-0.6b")
_DEFAULT_MEL = os.path.join(_ASR_UTILS, "resources", "mel_filters.bin")

LANGUAGE_MAP = {"zh": "Chinese", "en": "English", "ja": "Japanese"}


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

    model_dir = os.environ.get("GLM_ASR_MODEL", _DEFAULT_MODEL)
    fa_model_dir = os.environ.get("GLM_ASR_FA_MODEL", _DEFAULT_FA_MODEL)
    mel_path = os.environ.get("GLM_ASR_MEL", _DEFAULT_MEL)

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
            raise RuntimeError(
                f"glm-asr exited with code {result.returncode}: {stderr[:500]}"
            )

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
