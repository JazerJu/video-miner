"""
TTS (Text-to-Speech) utilities module
Provides audio synthesis from SRT subtitles using Alibaba Cloud CosyVoice-v2
"""

from .tts_generator import (
    synthesize_audio_from_srt,
    DEFAULT_VOICE,
    DEFAULT_MODEL,
)

__all__ = [
    'synthesize_audio_from_srt',
    'DEFAULT_VOICE',
    'DEFAULT_MODEL',
]
