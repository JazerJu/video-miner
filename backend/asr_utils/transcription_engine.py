# asr_utils/transcription_engine.py
"""
Unified transcription engine interface for VidGo
Supports multiple transcription engines with standardized interface
"""

from typing import Callable, Optional, Dict, Any
from abc import ABC, abstractmethod
from importlib import import_module

from asr_utils.hot_words import correct_srt_text


class TranscriptionEngine(ABC):
    """Abstract base class for all transcription engines"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def transcribe_audio(
        self,
        audio_file_path: str,
        progress_cb: Callable[[str], None],
        language: Optional[str] = None,
        subtitle_mode: str = "word",
    ) -> str:
        """
        Transcribe audio file to SRT format

        Args:
            audio_file_path: Path to audio file
            progress_cb: Progress callback function
            language: Optional language hint for transcription
            subtitle_mode: "word" for word-level, "sentence" for sentence-level

        Returns:
            SRT format string
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this engine is available and properly configured"""
        pass

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Return engine name"""
        pass


class ElevenLabsEngine(TranscriptionEngine):
    """ElevenLabs Speech-to-Text API engine"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        # Get ElevenLabs settings from config
        transcription_settings = config.get("Transcription Engine", {})
        self.api_key = transcription_settings.get("elevenlabs_api_key", "")

    def transcribe_audio(
        self,
        audio_file_path: str,
        progress_cb: Callable[[str], None],
        language: Optional[str] = None,
        subtitle_mode: str = "word",
    ) -> str:
        try:
            progress_cb("Running")
            from .elevenlab_wsr import elevenlabs_stt_to_word_srt
            from utils.split_subtitle.ASRData import merge_to_sentences_from_srt

            if not self.api_key:
                raise Exception("ElevenLabs API key not configured")

            transcription_settings = self.config.get("Transcription Engine", {})
            srt_content = elevenlabs_stt_to_word_srt(
                audio_path=audio_file_path,
                api_key=self.api_key,
                model_id=transcription_settings.get("elevenlabs_model", "scribe_v1"),
                include_punctuation=transcription_settings.get(
                    "include_punctuation", "false"
                ).lower()
                == "true",
            )

            if subtitle_mode == "sentence":
                srt_content = merge_to_sentences_from_srt(srt_content)

            progress_cb("Completed")
            return srt_content

        except Exception as e:
            progress_cb("Failed")
            raise Exception(f"ElevenLabs transcription failed: {str(e)}")

    def is_available(self) -> bool:
        return bool(self.api_key)

    @property
    def engine_name(self) -> str:
        return "elevenlabs"


class FunAsrGgufEngine(TranscriptionEngine):
    """FunASR-GGUF local engine (Fun-ASR-Nano: CTC hard-alignment + Qwen3 LLM decoder).

    Tighter word-level timestamps than Faster-Whisper's cross-attention approach,
    which improves the downstream LLM subtitle splitter quality.
    """

    def transcribe_audio(
        self,
        audio_file_path: str,
        progress_cb: Callable[[str], None],
        language: Optional[str] = None,
        subtitle_mode: str = "word",
    ) -> str:
        try:
            from .funasr_gguf_wsr import transcribe_audio, update_hotwords
            from utils.split_subtitle.ASRData import merge_to_sentences_from_srt

            hotwords_text = self.config.get("DEFAULT", {}).get("hotwords", "")
            update_hotwords(hotwords_text)
            srt_content = transcribe_audio(audio_file_path, progress_cb, language)

            if subtitle_mode == "sentence":
                srt_content = merge_to_sentences_from_srt(srt_content)

            return srt_content
        except Exception as e:
            raise Exception(f"FunASR-GGUF transcription failed: {str(e)}")

    def is_available(self) -> bool:
        try:
            from .funasr_gguf_wsr import is_available

            return is_available()
        except Exception:
            return False

    @property
    def engine_name(self) -> str:
        return "funasr_gguf"


class GlmAsrEngine(TranscriptionEngine):
    """GLM-ASR Stack: full pipeline (ASR + ForceAligner) with sentence-level SRT output."""

    def transcribe_audio(
        self,
        audio_file_path: str,
        progress_cb: Callable[[str], None],
        language: Optional[str] = None,
        subtitle_mode: str = "word",
    ) -> str:
        try:
            glm_asr_wsr = import_module(".glm_asr_wsr", __package__)
            transcribe_audio = glm_asr_wsr.transcribe_audio

            return transcribe_audio(audio_file_path, progress_cb, language, subtitle_mode)
        except Exception as e:
            raise Exception(f"GLM-ASR transcription failed: {str(e)}")

    def is_available(self) -> bool:
        try:
            glm_asr_wsr = import_module(".glm_asr_wsr", __package__)
            is_available = glm_asr_wsr.is_available

            return is_available()
        except Exception:
            return False

    @property
    def engine_name(self) -> str:
        return "glm_asr"


class TranscriptionEngineFactory:
    """Factory class for creating transcription engines"""

    _engines = {
        "funasr_gguf": FunAsrGgufEngine,
        "glm_asr": GlmAsrEngine,
        "elevenlabs": ElevenLabsEngine,
    }

    @classmethod
    def create_engine(
        cls, engine_type: str, config: Dict[str, Any]
    ) -> TranscriptionEngine:
        """Create a transcription engine instance"""
        if engine_type not in cls._engines:
            available_engines = ", ".join(cls._engines.keys())
            raise ValueError(
                f"Unknown engine type '{engine_type}'. Available: {available_engines}"
            )

        engine_class = cls._engines[engine_type]
        return engine_class(config)

    @classmethod
    def get_available_engines(cls, config: Dict[str, Any]) -> list[str]:
        """Get list of available and properly configured engines"""
        available = []
        for engine_type in cls._engines:
            try:
                engine = cls.create_engine(engine_type, config)
                if engine.is_available():
                    available.append(engine_type)
            except Exception:
                continue
        return available

    @classmethod
    def get_engine_info(cls) -> Dict[str, Dict[str, Any]]:
        """Get information about all supported engines"""
        return {
            "funasr_gguf": {
                "name": "FunASR-GGUF (Fun-ASR-Nano, CTC + Qwen3 decoder)",
                "description": "Local FunASR with GGUF Q5_K + ONNX INT4 quantization. Tighter word timestamps via CTC hard-alignment, optimized for Chinese.",
                "type": "local",
                "languages": "Chinese/English (Fun-ASR-Nano)",
                "requires_api_key": False,
                "speed": "Fast (CUDA/CPU)",
                "quality": "High (especially Chinese)",
            },
            "glm_asr": {
                "name": "GLM-ASR Stack (GLM-ASR-Nano + Qwen3 ForcedAligner)",
                "description": "Local ASR with sentence-level timestamps via ForceAligner. Full pipeline: ASR + alignment + sentence segmentation.",
                "type": "local",
                "languages": "Chinese/English/Japanese",
                "requires_api_key": False,
                "speed": "Very Fast (CUDA)",
                "quality": "High",
            },
            "elevenlabs": {
                "name": "ElevenLabs Speech-to-Text",
                "type": "api",
                "languages": "Multi-language",
                "requires_api_key": True,
                "speed": "Fast",
                "quality": "High",
            },
        }


def load_transcription_settings():
    """Load transcription engine settings using existing load_all_settings function"""
    try:
        set_setting = import_module("video.views.set_setting")
        load_all_settings = set_setting.load_all_settings

        return load_all_settings()
    except Exception as e:
        print(f"Error loading transcription settings: {e}")
        return {}


def _apply_hotword_correction(srt_content: str, config: Dict[str, Any]) -> str:
    hotwords = config.get("DEFAULT", {}).get("hotwords", "")
    if hotwords.strip():
        srt_content = correct_srt_text(srt_content, hotwords)
        print("Applied hotword correction")
    return srt_content


def transcribe_with_engine(
    engine_type: str,
    audio_file_path: str,
    progress_cb: Callable[[str], None],
    fallback_engine: Optional[str] = None,
    language: Optional[str] = None,
    subtitle_mode: str = "word",
) -> str:
    """
    Transcribe audio using specified engine with optional fallback

    Args:
        engine_type: Primary engine to use
        audio_file_path: Path to audio file
        progress_cb: Progress callback
        fallback_engine: Fallback engine if primary fails
        language: Language hint
        subtitle_mode: "word" for word-level, "sentence" for sentence-level

    Returns:
        SRT content string
    """
    config = load_transcription_settings()

    try:
        engine = TranscriptionEngineFactory.create_engine(engine_type, config)
        if not engine.is_available():
            raise Exception(
                f"Engine '{engine_type}' is not available or not properly configured"
            )

        print(f"Using transcription engine: {engine.engine_name}")
        srt_content = engine.transcribe_audio(
            audio_file_path,
            progress_cb,
            language,
            subtitle_mode,
        )
        return _apply_hotword_correction(srt_content, config)

    except Exception as primary_error:
        print(f"Primary engine '{engine_type}' failed: {primary_error}")

        if fallback_engine and fallback_engine != engine_type:
            try:
                print(f"Trying fallback engine: {fallback_engine}")
                fallback_engine_instance = TranscriptionEngineFactory.create_engine(
                    fallback_engine, config
                )
                if fallback_engine_instance.is_available():
                    srt_content = fallback_engine_instance.transcribe_audio(
                        audio_file_path, progress_cb, language, subtitle_mode
                    )
                    return _apply_hotword_correction(srt_content, config)
                else:
                    raise Exception(
                        f"Fallback engine '{fallback_engine}' is not available"
                    )
            except Exception as fallback_error:
                raise Exception(
                    f"Both primary and fallback engines failed. Primary: {primary_error}, Fallback: {fallback_error}"
                )
        else:
            raise primary_error
