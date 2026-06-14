"""
FunASR-GGUF adapter for VidGo.

Wraps the local FunASR-GGUF model (Fun-ASR-Nano, Qwen3-0.6B decoder + SenseVoice
encoder, GGUF Q5_K + ONNX INT4) so it satisfies VidGo's TranscriptionEngine contract:
  - transcribe_audio(path, progress_cb, language=None) -> SRT string
  - is_available() -> bool
  - engine_name property

Why this exists: Faster-Whisper's word_timestamps are based on cross-attention
soft-alignment (approximate). FunASR-GGUF uses CTC hard-alignment, which produces
tighter word boundaries — important for the downstream LLM subtitle splitter.
"""

import os
import sys
import threading
from importlib import import_module
from pathlib import Path
from typing import Callable, Optional

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_FUNASR_STACK_DIR = _BACKEND_DIR / "asr_utils" / "fun-asr-stack"
_MODELS_DIR = _BACKEND_DIR / "models" / "fun-asr"

FUNASR_GGUF_DIR = Path(os.environ.get("FUNASR_GGUF_DIR", str(_FUNASR_STACK_DIR)))

_ENCODER_PATH = _MODELS_DIR / "Fun-ASR-Nano-Encoder-Adaptor.fp16.onnx"
_CTC_PATH = _MODELS_DIR / "Fun-ASR-Nano-CTC.fp16.onnx"
_DECODER_PATH = _MODELS_DIR / "Fun-ASR-Nano-Decoder.q5_k.gguf"
_TOKENS_PATH = _MODELS_DIR / "tokens.txt"

LANGUAGE_CODE_TO_FUNASR = {"zh": "中文", "en": "英文"}

_engine_lock = threading.Lock()
_engine_use_lock = threading.Lock()
_engine_instance = None
_engine_init_failed = False
_engine_init_error: Optional[str] = None
_hotwords_lock = threading.Lock()
_hotwords_engine_id: Optional[int] = None
_hotwords_signature: tuple[str, ...] = ()


def _import_funasr_gguf():
    if not FUNASR_GGUF_DIR.exists():
        raise FileNotFoundError(
            f"FunASR-GGUF directory not found: {FUNASR_GGUF_DIR}. "
            "Set FUNASR_GGUF_DIR env var to override."
        )
    if str(FUNASR_GGUF_DIR) not in sys.path:
        sys.path.insert(0, str(FUNASR_GGUF_DIR))
    funasr_gguf = import_module("fun_asr_gguf")
    return funasr_gguf.FunASREngine, funasr_gguf.ASREngineConfig


def _get_engine():
    """Lazy singleton with thread-safe init. Re-init is attempted at most once
    per process; persistent failures are cached to avoid repeating the cost.
    """
    global _engine_instance, _engine_init_failed, _engine_init_error
    if _engine_instance is not None:
        return _engine_instance
    if _engine_init_failed:
        raise RuntimeError(
            f"FunASR-GGUF engine previously failed to initialize: {_engine_init_error}"
        )
    with _engine_lock:
        if _engine_instance is not None:
            return _engine_instance
        try:
            FunASREngine, ASREngineConfig = _import_funasr_gguf()
            config = ASREngineConfig(
                encoder_onnx_path=str(_ENCODER_PATH),
                ctc_onnx_path=str(_CTC_PATH),
                decoder_gguf_path=str(_DECODER_PATH),
                tokens_path=str(_TOKENS_PATH),
                onnx_provider='CUDA',
            )
            _engine_instance = FunASREngine(config)
        except Exception as e:
            _engine_init_failed = True
            _engine_init_error = str(e)
            raise
    return _engine_instance


def is_available() -> bool:
    try:
        if not (
            _ENCODER_PATH.exists()
            and _CTC_PATH.exists()
            and _DECODER_PATH.exists()
            and _TOKENS_PATH.exists()
        ):
            return False
        _import_funasr_gguf()
        return True
    except Exception:
        return False


def _parse_hotwords(hotwords_text: str) -> list[str]:
    return [
        hotword
        for hotword in (line.strip() for line in hotwords_text.splitlines())
        if hotword and not hotword.startswith("#")
    ]


def update_hotwords(hotwords_text: str) -> None:
    hotwords = _parse_hotwords(hotwords_text or "")
    if not hotwords:
        return

    engine = _get_engine()
    engine_id = id(engine)
    signature = tuple(hotwords)

    global _hotwords_engine_id, _hotwords_signature
    with _hotwords_lock:
        if _hotwords_engine_id == engine_id and _hotwords_signature == signature:
            return

        with _engine_use_lock:
            engine.update_hotwords(hotwords)
        _hotwords_engine_id = engine_id
        _hotwords_signature = signature


def _extract_srt(asr_result) -> str:
    """FunASR's transcribe() can return either a string SRT or a result object
    exposing .srt / .text. Handle both, and rebuild SRT from segments if needed.

    Fun-ASR segments format: flat list of [character, start_time] pairs.
    Each character gets its own SRT entry with end_time = next char's start_time.
    """
    if isinstance(asr_result, str):
        return asr_result
    srt = getattr(asr_result, "srt", None)
    if srt:
        return srt
    segments = getattr(asr_result, "segments", None)
    if not segments:
        text = getattr(asr_result, "text", "")
        return text or ""

    from utils.video.time_convert import seconds_to_srt_time

    # Detect flat [char, start_time] list format from Fun-ASR
    if segments and isinstance(segments[0], list) and len(segments[0]) == 2:
        import re
        _SENT_END = re.compile(r'[。！？!?；;]')
        _CLAUSE_END = re.compile(r'[，,、）)】]')

        out = []
        idx = 1
        buf_chars = []
        buf_start = None

        for i, (char, start) in enumerate(segments):
            text_c = char if isinstance(char, str) else str(char)
            if not buf_start:
                buf_start = start
            buf_chars.append(text_c)

            next_start = segments[i + 1][1] if i + 1 < len(segments) else start + 0.5
            gap = next_start - start
            is_sent_end = bool(_SENT_END.search(text_c))
            is_clause_end = bool(_CLAUSE_END.search(text_c))
            merged = "".join(buf_chars).strip()

            should_flush = (
                is_sent_end
                or (is_clause_end and len(merged) >= 15)
                or (gap > 0.8 and len(merged) >= 5)
                or len(merged) >= 40
            )

            if should_flush and merged:
                end = next_start if gap > 0.8 else next_start + 0.01
                if end <= buf_start:
                    end = buf_start + 0.5
                out.append(
                    f"{idx}\n{seconds_to_srt_time(buf_start)} --> "
                    f"{seconds_to_srt_time(end)}\n{merged}\n"
                )
                idx += 1
                buf_chars = []
                buf_start = None

        if buf_chars:
            merged = "".join(buf_chars).strip()
            if merged:
                end = segments[-1][1] + 0.5
                out.append(
                    f"{idx}\n{seconds_to_srt_time(buf_start)} --> "
                    f"{seconds_to_srt_time(end)}\n{merged}\n"
                )

        return "\n".join(out) + ("\n" if out else "")

    # Structured segment objects (has .start/.end/.text/.words attributes)
    text = getattr(asr_result, "text", "")
    out = []
    idx = 1
    for seg in segments:
        start = getattr(seg, "start", 0.0) or 0.0
        end = getattr(seg, "end", start) or start
        words = getattr(seg, "words", None)
        if words:
            for w in words:
                ws = getattr(w, "start", start) or start
                we = getattr(w, "end", end) or end
                wt = (getattr(w, "word", None) or getattr(w, "text", "") or "").strip()
                if not wt:
                    continue
                out.append(
                    f"{idx}\n{seconds_to_srt_time(ws)} --> "
                    f"{seconds_to_srt_time(we)}\n{wt}\n"
                )
                idx += 1
        else:
            st = (getattr(seg, "text", "") or text or "").strip()
            if not st:
                continue
            out.append(
                f"{idx}\n{seconds_to_srt_time(start)} --> "
                f"{seconds_to_srt_time(end)}\n{st}\n"
            )
            idx += 1
    return "\n".join(out) + ("\n" if out else "")


def transcribe_audio(
    audio_file_path: str,
    progress_cb: Callable[[str], None],
    language: Optional[str] = None,
) -> str:
    progress_cb("Running")
    engine = _get_engine()
    lang_arg = LANGUAGE_CODE_TO_FUNASR.get(language, language) if language else None
    with _engine_use_lock:
        result = engine.transcribe(audio_file_path, language=lang_arg, srt=True)
    srt = _extract_srt(result)
    if not srt:
        raise RuntimeError("FunASR-GGUF returned empty SRT")
    progress_cb("Completed")
    return srt
