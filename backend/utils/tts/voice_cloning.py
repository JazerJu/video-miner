"""
Voice Cloning Utilities for TTS
Handles voice model creation using Alibaba Cloud DashScope CosyVoice API
"""
import time
import hashlib
import json
import os
from typing import Optional
import dashscope
from dashscope.audio.tts_v2 import VoiceEnrollmentService
from video.views.set_setting import load_all_settings


# Cache for voice IDs to avoid recreating models for the same audio
VOICE_ID_CACHE = {}
CACHE_FILE = "work_dir/tts_voice_cache.json"


def load_voice_cache():
    """Load voice ID cache from file"""
    global VOICE_ID_CACHE
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                VOICE_ID_CACHE = json.load(f)
    except Exception as e:
        print(f"[Voice Cloning] Error loading cache: {e}")
        VOICE_ID_CACHE = {}


def save_voice_cache():
    """Save voice ID cache to file"""
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(VOICE_ID_CACHE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Voice Cloning] Error saving cache: {e}")


def get_voice_cache_key(audio_url: str, reference_text: str = "") -> str:
    """Generate cache key for voice model"""
    content = f"{audio_url}|{reference_text}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def create_voice_from_audio(
    audio_url: str,
    reference_text: str = "",
    voice_name: str = "custom_voice",
    model: str = "cosyvoice-v2"
) -> str:
    """
    Create voice model from reference audio URL using DashScope VoiceEnrollmentService

    Args:
        audio_url: Publicly accessible URL to reference audio file
        reference_text: Text content of the reference audio (optional but recommended)
        voice_name: Name prefix for the voice model
        model: Target model for voice cloning (default: cosyvoice-v2)

    Returns:
        voice_id: ID of the created voice model

    Raises:
        Exception: If voice creation fails
    """
    global VOICE_ID_CACHE

    # Load cache
    load_voice_cache()

    # Check cache first
    cache_key = get_voice_cache_key(audio_url, reference_text)
    if cache_key in VOICE_ID_CACHE:
        cached_voice_id = VOICE_ID_CACHE[cache_key]
        print(f"[Voice Cloning] Using cached voice ID: {cached_voice_id}")
        return cached_voice_id

    # Load DashScope API key
    settings_data = load_all_settings()
    tts_settings = settings_data.get('TTS settings', {})
    api_key = tts_settings.get('dashscope_api_key', '')

    if not api_key:
        raise Exception("DashScope API key not configured")

    # Initialize VoiceEnrollmentService
    dashscope.api_key = api_key
    svc = VoiceEnrollmentService()

    # Ensure voice name is valid (alphanumeric, max 10 chars)
    import re
    alphanumeric_name = re.sub(r'[^a-zA-Z0-9]', '', voice_name)
    short_prefix = alphanumeric_name[:10] if len(alphanumeric_name) > 10 else alphanumeric_name
    # Ensure we have at least one character
    if not short_prefix:
        short_prefix = "clone"

    print(f"[Voice Cloning] Creating voice model with prefix: {short_prefix}")
    print(f"[Voice Cloning] Audio URL: {audio_url}")
    print(f"[Voice Cloning] Reference text: {reference_text}")

    # Create voice model
    try:
        voice_id = svc.create_voice(
            target_model=model,
            prefix=short_prefix,
            url=audio_url
        )

        if not voice_id:
            raise Exception("VoiceEnrollmentService returned empty voice_id")

        print(f"[Voice Cloning] Voice created successfully: {voice_id}")

        # Cache the voice ID
        VOICE_ID_CACHE[cache_key] = voice_id
        save_voice_cache()

        return voice_id

    except Exception as e:
        print(f"[Voice Cloning] Error creating voice: {e}")
        raise Exception(f"Failed to create voice model: {str(e)}")


def wait_for_voice_ready(voice_id: str, max_wait_time: int = 30) -> bool:
    """
    Wait for voice model to be ready for use

    Args:
        voice_id: ID of the voice model to check
        max_wait_time: Maximum time to wait in seconds (default: 30)

    Returns:
        bool: True if voice is ready, False if timeout
    """
    # For now, we'll just wait a fixed amount of time
    # In the future, we could check the voice status through the API
    print(f"[Voice Cloning] Waiting for voice model to be ready...")
    time.sleep(2)  # Short wait to ensure server-side processing
    return True