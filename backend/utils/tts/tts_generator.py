# -*- coding: utf-8 -*-
"""
TTS Generator Module
Converts SRT subtitles to speech using Alibaba Cloud CosyVoice-v2
Extracted and adapted from test/generate_audio/srt-gen-qwen-tts.py

Enhanced with:
- Retry mechanism with exponential backoff
- Progress checkpointing for crash recovery
- Dynamic rate limiting based on success rate
- Graceful degradation with partial results

cosyvoice api : https://www.alibabacloud.com/help/zh/model-studio/cosyvoice-clone-api
voice options in https://www.alibabacloud.com/help/zh/model-studio/cosyvoice-python-sdk
"""

import os
import io
import re
import time
import hashlib
import json
import random
from pathlib import Path
from typing import List, Optional, Tuple, Callable, Dict, Any
from functools import wraps
from dataclasses import dataclass, asdict

import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer, ResultCallback, AudioFormat
from pydub import AudioSegment

# Import ASRData for SRT parsing
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'split_subtitle'))
from ASRData import ASRDataSeg, from_srt

# Import time-stretch module for pitch-preserving audio adjustment
from .audio_time_stretch import stretch_audio, get_available_algorithms


# Constants
DEFAULT_MODEL = "cosyvoice-v2"
DEFAULT_VOICE = "longxiaochun_v2"
TARGET_SAMPLE_RATE = 22050  # CosyVoice-v2 sample rate
TTS_REQUEST_INTERVAL = 0.5  # Base rate limiting (seconds)

# Retry configuration
MAX_RETRIES = 5
INITIAL_BACKOFF = 2.0  # seconds
MAX_BACKOFF = 32.0  # seconds
BACKOFF_MULTIPLIER = 2.0
JITTER_MAX = 2.0  # seconds

# Checkpoint configuration
CHECKPOINT_INTERVAL = 10  # Save progress every N segments

# Cache directory
CACHE_DIR = Path(__file__).parent.parent.parent / "work_dir" / "tts_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ===================== Robustness Classes =====================

@dataclass
class TTSCheckpoint:
    """Checkpoint data for TTS progress recovery"""
    task_id: str
    total_segments: int
    completed_segments: List[int]  # Indices of completed segments
    audio_files: Dict[int, str]  # segment_index -> audio_file_path
    timestamp: float

    def save(self, checkpoint_path: str):
        """Save checkpoint to file"""
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, checkpoint_path: str) -> Optional['TTSCheckpoint']:
        """Load checkpoint from file"""
        if not os.path.exists(checkpoint_path):
            return None
        try:
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return cls(**data)
        except Exception as e:
            print(f"⚠️  Failed to load checkpoint: {e}")
            return None


class DynamicRateLimiter:
    """Adaptive rate limiter based on API success rate"""

    def __init__(self, base_interval: float = TTS_REQUEST_INTERVAL):
        self.base_interval = base_interval
        self.current_interval = base_interval
        self.recent_failures = []  # Timestamps of recent failures
        self.consecutive_failures = 0
        self.circuit_open = False
        self.circuit_open_until = 0

    def wait(self):
        """Wait appropriate interval before next request"""
        # Check circuit breaker
        if self.circuit_open:
            if time.time() < self.circuit_open_until:
                wait_time = self.circuit_open_until - time.time()
                print(f"⏸️  Circuit breaker active, waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
            self.circuit_open = False

        time.sleep(self.current_interval)

    def record_success(self):
        """Record successful API call"""
        self.consecutive_failures = 0
        # Gradually decrease interval back to base
        self.current_interval = max(
            self.base_interval,
            self.current_interval * 0.9
        )

    def record_failure(self):
        """Record failed API call and adjust interval"""
        self.consecutive_failures += 1
        self.recent_failures.append(time.time())

        # Remove old failures (older than 60s)
        cutoff = time.time() - 60
        self.recent_failures = [t for t in self.recent_failures if t > cutoff]

        # Increase interval based on recent failure rate
        failure_count = len(self.recent_failures)
        if failure_count >= 10:
            # Circuit breaker: pause for 30s
            self.circuit_open = True
            self.circuit_open_until = time.time() + 30
            print(f"🔴 Circuit breaker opened due to {failure_count} failures in 60s")
        elif failure_count >= 5:
            self.current_interval = min(5.0, self.base_interval * 3)
        elif failure_count >= 3:
            self.current_interval = min(3.0, self.base_interval * 2)


def retry_with_backoff(max_retries: int = MAX_RETRIES):
    """
    Retry decorator with exponential backoff and jitter

    Handles specific exceptions:
    - SSL errors: Retry with longer timeout
    - Websocket timeouts: Retry immediately
    - Rate limits: Wait and retry
    - Other errors: Fail after max retries
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)

                except Exception as e:
                    last_exception = e
                    error_str = str(e).lower()

                    # Determine if we should retry
                    is_ssl_error = 'ssl' in error_str or 'eof' in error_str
                    is_websocket_error = 'websocket' in error_str
                    is_rate_limit = 'rate limit' in error_str or '429' in error_str

                    if attempt == max_retries - 1:
                        # Last attempt, give up
                        print(f"❌ Max retries ({max_retries}) exceeded: {e}")
                        raise

                    # Calculate backoff time
                    if is_rate_limit:
                        backoff = 10.0  # Wait 10s for rate limits
                    elif is_websocket_error:
                        backoff = INITIAL_BACKOFF * (BACKOFF_MULTIPLIER ** attempt)
                    elif is_ssl_error:
                        backoff = INITIAL_BACKOFF * (BACKOFF_MULTIPLIER ** attempt)
                    else:
                        backoff = INITIAL_BACKOFF * (BACKOFF_MULTIPLIER ** attempt)

                    # Add jitter to avoid thundering herd
                    jitter = random.uniform(0, JITTER_MAX)
                    total_wait = min(backoff + jitter, MAX_BACKOFF)

                    print(f"⚠️  Attempt {attempt + 1}/{max_retries} failed: {e}")
                    print(f"   Retrying in {total_wait:.1f}s...")
                    time.sleep(total_wait)

            # Should never reach here, but just in case
            raise last_exception

        return wrapper
    return decorator


# ===================== Helper Functions =====================

def count_words(text: str) -> int:
    """Count words in text (Chinese characters + English words)"""
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    english_words = len(re.findall(r'\b[a-zA-Z]+\b', text))
    return chinese_chars + english_words


def merge_segments(
    segments: List[ASRDataSeg],
    max_duration_ms: int = 15000,
    max_words: int = 50
) -> List[ASRDataSeg]:
    """
    Merge adjacent subtitle segments to optimize TTS calls

    Args:
        segments: List of subtitle segments
        max_duration_ms: Maximum merged segment duration (default 15s)
        max_words: Maximum word count per merged segment (default 50)

    Returns:
        List of merged segments
    """
    if not segments:
        return []

    merged = []
    current = segments[0]

    for i in range(1, len(segments)):
        next_seg = segments[i]

        # Check if can merge
        can_merge = (
            current.end_time == next_seg.start_time and
            (next_seg.end_time - current.start_time) < max_duration_ms and
            count_words(current.text + next_seg.text) < max_words
        )

        if can_merge:
            # Merge text
            merged_text = current.text + next_seg.text
            current = ASRDataSeg(
                text=merged_text,
                start_time=current.start_time,
                end_time=next_seg.end_time,
                direct=current.direct,
                free=current.free,
                reflected=current.reflected
            )
        else:
            merged.append(current)
            current = next_seg

    # Add last segment
    merged.append(current)
    return merged


def silent_segment(duration_ms: int, sr: int = TARGET_SAMPLE_RATE) -> AudioSegment:
    """Create silent audio segment"""
    return AudioSegment.silent(duration=duration_ms, frame_rate=sr).set_channels(1).set_sample_width(2)


def bytes_to_segment(audio_bytes: bytes) -> AudioSegment:
    """
    Convert PCM bytes to AudioSegment
    CosyVoice-v2 returns PCM_22050HZ_MONO_16BIT format
    """
    if not audio_bytes:
        return silent_segment(10)

    return AudioSegment(
        data=audio_bytes,
        sample_width=2,  # 16bit
        frame_rate=22050,
        channels=1
    )


def adjust_audio_duration(
    audio_seg: AudioSegment,
    target_duration_ms: int,
    tolerance: float = 0.2,
    fade_ms: int = 100,
    stretch_algorithm: str = 'librosa',
    stretch_quality: str = 'high',
    max_stretch_ratio: float = 2.0
) -> AudioSegment:
    """
    Adjust audio duration with adaptive strategy:
    - If audio is shorter: Pad with silence and smooth fade transitions
    - If audio is longer: Time-stretch with pitch preservation (preserves tone color)

    Args:
        audio_seg: Input audio segment
        target_duration_ms: Target duration in milliseconds
        tolerance: Acceptable duration ratio difference (default 20%)
        fade_ms: Fade duration for smooth transitions when padding (default 100ms)
        stretch_algorithm: Algorithm for time-stretching ('librosa', 'rubberband', 'resample')
        stretch_quality: Quality for librosa ('low', 'medium', 'high')
        max_stretch_ratio: Maximum stretch ratio before warning (default 2.0)

    Returns:
        AudioSegment adjusted to target duration

    Examples:
        - Audio 8s, target 10s -> pad with 2s silence + fade transitions
        - Audio 12s, target 10s -> time-stretch to 10s (preserves pitch/tone)
        - Audio 10.1s, target 10s (within tolerance) -> no change
    """
    audio_duration_ms = len(audio_seg)

    # Skip if duration is within tolerance
    if abs(audio_duration_ms - target_duration_ms) / target_duration_ms < tolerance:
        return audio_seg

    # Case 1: Audio is SHORTER than target -> Pad with silence + smooth transition
    if audio_duration_ms < target_duration_ms:
        padding_needed = target_duration_ms - audio_duration_ms

        print(f"  🔇 Padding audio: {audio_duration_ms}ms -> {target_duration_ms}ms (adding {padding_needed}ms silence)")

        # Apply fade out to the end of audio for smooth transition
        fade_duration = min(fade_ms, len(audio_seg) // 2)
        audio_with_fade = audio_seg.fade_out(duration=fade_duration)

        # Create silence padding
        silence = silent_segment(padding_needed, sr=audio_seg.frame_rate)

        # Combine: audio with fade-out + silence
        adjusted_seg = audio_with_fade + silence

        return adjusted_seg

    # Case 2: Audio is LONGER than target -> Time-stretch (preserves pitch)
    else:
        print(f"  ⏱️  Time-stretching: {audio_duration_ms}ms -> {target_duration_ms}ms (algorithm: {stretch_algorithm})")

        # Use pitch-preserving time-stretch algorithm
        adjusted_seg = stretch_audio(
            audio_seg=audio_seg,
            target_duration_ms=target_duration_ms,
            algorithm=stretch_algorithm,
            quality=stretch_quality,
            max_ratio=max_stretch_ratio,
            warn_on_extreme=True
        )

        return adjusted_seg


# ===================== TTS API Integration =====================

class AudioCollectorCallback(ResultCallback):
    """Callback to collect streaming audio data"""
    def __init__(self):
        self.audio_data = io.BytesIO()
        self.error_msg = None

    def on_open(self):
        pass

    def on_complete(self):
        pass

    def on_error(self, message: str):
        self.error_msg = message
        print(f"❌ TTS Error: {message}")

    def on_close(self):
        pass

    def on_event(self, message):
        pass

    def on_data(self, data: bytes) -> None:
        self.audio_data.write(data)


@retry_with_backoff(max_retries=MAX_RETRIES)
def tts_bytes_cosyvoice(
    text: str,
    api_key: str,
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
    rate_limiter: Optional[DynamicRateLimiter] = None,
) -> Optional[bytes]:
    """
    Synthesize audio using CosyVoice streaming API

    Args:
        text: Text to synthesize
        api_key: Alibaba Cloud API key
        voice: Voice ID
        model: Model name
        rate_limiter: Optional dynamic rate limiter

    Returns:
        PCM audio bytes
    """
    if not text.strip():
        return b""

    # Dynamic rate limiting
    if rate_limiter:
        rate_limiter.wait()
    else:
        time.sleep(TTS_REQUEST_INTERVAL)

    callback = AudioCollectorCallback()

    # Set global API key
    if api_key:
        dashscope.api_key = api_key

    try:
        synthesizer = SpeechSynthesizer(
            model=model,
            voice=voice,
            format=AudioFormat.PCM_22050HZ_MONO_16BIT,
            callback=callback,
        )

        # Stream text
        synthesizer.streaming_call(text)
        synthesizer.streaming_complete()

        if callback.error_msg:
            raise RuntimeError(f"TTS synthesis failed: {callback.error_msg}")

        # Record success for rate limiter
        if rate_limiter:
            rate_limiter.record_success()

        return callback.audio_data.getvalue()

    except Exception as e:
        # Record failure for rate limiter
        if rate_limiter:
            rate_limiter.record_failure()

        print(f"❌ TTS synthesis exception: {e}")
        raise


# ===================== Caching System =====================

def get_cache_key(text: str, voice: str, model: str) -> str:
    """Generate MD5 cache key"""
    content = f"{text}|{voice}|{model}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def load_cached_audio(cache_key: str) -> Optional[AudioSegment]:
    """Load audio from cache"""
    cache_file = CACHE_DIR / f"{cache_key}.wav"
    if cache_file.exists():
        try:
            return AudioSegment.from_file(str(cache_file), format="wav")
        except Exception as e:
            print(f"⚠️  Cache read failed: {e}")
            return None
    return None


def save_cached_audio(cache_key: str, audio_seg: AudioSegment):
    """Save audio to cache"""
    cache_file = CACHE_DIR / f"{cache_key}.wav"
    try:
        audio_seg.export(str(cache_file), format="wav")
    except Exception as e:
        print(f"⚠️  Cache save failed: {e}")


def tts_to_segment(
    text: str,
    api_key: str,
    voice: str,
    model: str,
    rate_limiter: Optional[DynamicRateLimiter] = None,
) -> AudioSegment:
    """
    Synthesize audio segment with caching

    Args:
        text: Text to synthesize
        api_key: API key
        voice: Voice ID
        model: Model name
        rate_limiter: Optional dynamic rate limiter

    Returns:
        AudioSegment
    """
    # Check cache
    cache_key = get_cache_key(text, voice, model)
    cached = load_cached_audio(cache_key)
    if cached:
        print(f"  💾 Using cache")
        return cached.set_frame_rate(TARGET_SAMPLE_RATE).set_channels(1)

    # TTS synthesis with retry and rate limiting
    pcm_bytes = tts_bytes_cosyvoice(
        text,
        api_key=api_key,
        voice=voice,
        model=model,
        rate_limiter=rate_limiter
    )
    seg = bytes_to_segment(pcm_bytes)

    # Save to cache
    save_cached_audio(cache_key, seg)

    return seg


# ===================== Main TTS Generation Function =====================

def synthesize_audio_from_srt(
    srt_path: str,
    output_wav: str,
    api_key: str,
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
    min_gap_ms: int = 100,
    crossfade_ms: int = 50,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    task_id: Optional[str] = None,
    enable_checkpointing: bool = True,
    max_retries_per_segment: int = MAX_RETRIES,
    # Time-stretch configuration
    time_stretch_algorithm: str = 'librosa',
    time_stretch_quality: str = 'high',
    max_compression_ratio: float = 2.0,
) -> Tuple[int, int]:
    """
    Main function: Synthesize audio from SRT subtitle file

    Enhanced with:
    - Progress checkpointing for crash recovery
    - Dynamic rate limiting
    - Graceful degradation on failures
    - Partial result export

    Args:
        srt_path: Path to SRT file
        output_wav: Output WAV file path
        api_key: Alibaba Cloud API key
        voice: Voice ID (default: longxiaochun_v2)
        model: Model name (default: cosyvoice-v2)
        min_gap_ms: Minimum silence gap (default: 100ms)
        crossfade_ms: Crossfade duration (default: 50ms)
        progress_callback: Callback function(completed, total)
        task_id: Optional task ID for checkpointing
        enable_checkpointing: Enable progress checkpointing
        max_retries_per_segment: Max retry attempts per segment
        time_stretch_algorithm: Time-stretch algorithm ('librosa', 'rubberband', 'resample')
        time_stretch_quality: Quality for librosa ('low', 'medium', 'high')
        max_compression_ratio: Maximum compression ratio before warning

    Returns:
        Tuple of (segment_count, total_duration_ms)
    """
    # Initialize rate limiter
    rate_limiter = DynamicRateLimiter()

    # Load and merge SRT
    with open(srt_path, 'r', encoding='utf-8') as f:
        asr_data = from_srt(f.read())

    segments = merge_segments(asr_data.segments)
    total_segments = len(segments)

    if total_segments == 0:
        raise ValueError("No subtitle segments found in SRT file")

    print(f"✅ Loaded subtitles: {len(asr_data.segments)} → merged to {total_segments} segments")

    # Checkpoint setup
    checkpoint_path = None
    checkpoint = None
    completed_segments = set()
    audio_segments = {}  # segment_index -> AudioSegment

    if enable_checkpointing and task_id:
        checkpoint_dir = Path(output_wav).parent
        checkpoint_path = checkpoint_dir / f"{task_id}_checkpoint.json"

        # Try to load existing checkpoint
        checkpoint = TTSCheckpoint.load(str(checkpoint_path))
        if checkpoint:
            completed_segments = set(checkpoint.completed_segments)
            print(f"🔄 Resuming from checkpoint: {len(completed_segments)}/{total_segments} segments completed")

            # Load cached audio segments
            for idx, audio_file in checkpoint.audio_files.items():
                if os.path.exists(audio_file):
                    try:
                        audio_segments[int(idx)] = AudioSegment.from_file(audio_file, format="wav")
                    except Exception as e:
                        print(f"⚠️  Failed to load cached segment {idx}: {e}")

    # Track failed segments
    failed_segments = []

    timeline = silent_segment(0)
    cursor_ms = 0

    for i, seg_data in enumerate(segments):
        segment_index = i

        # Skip if already completed
        if segment_index in completed_segments:
            print(f"[{i+1}/{total_segments}] ⏭️  Skipping completed segment")
            # Restore from cache
            if segment_index in audio_segments:
                seg = audio_segments[segment_index]
                # Re-add to timeline
                gap = seg_data.start_time - cursor_ms
                if gap > min_gap_ms:
                    adjusted_gap = max(min_gap_ms, gap - crossfade_ms)
                    timeline += silent_segment(adjusted_gap)
                    cursor_ms += adjusted_gap

                if len(timeline) > 0 and crossfade_ms > 0:
                    actual_crossfade = min(crossfade_ms, len(seg) // 2)
                    timeline = timeline.append(seg, crossfade=actual_crossfade)
                    cursor_ms += len(seg) - actual_crossfade
                else:
                    timeline += seg
                    cursor_ms += len(seg)

            if progress_callback:
                progress_callback(len(completed_segments), total_segments)
            continue

        preview = (seg_data.text[:28] + "...") if len(seg_data.text) > 28 else seg_data.text
        print(f"[{i+1}/{total_segments}] Synthesizing: {preview}")

        # Smart silence insertion
        gap = seg_data.start_time - cursor_ms
        if gap > min_gap_ms:
            adjusted_gap = max(min_gap_ms, gap - crossfade_ms)
            timeline += silent_segment(adjusted_gap)
            cursor_ms += adjusted_gap

        # Try to synthesize segment with retry
        try:
            seg = tts_to_segment(
                seg_data.text,
                api_key=api_key,
                voice=voice,
                model=model,
                rate_limiter=rate_limiter,
            )

            # Adjust audio duration with pitch-preserving time-stretch
            target_duration_ms = max(10, seg_data.end_time - seg_data.start_time)
            seg = adjust_audio_duration(
                seg,
                target_duration_ms,
                tolerance=0.2,
                stretch_algorithm=time_stretch_algorithm,
                stretch_quality=time_stretch_quality,
                max_stretch_ratio=max_compression_ratio
            )

            # Save segment for checkpointing
            audio_segments[segment_index] = seg

        except Exception as e:
            print(f"❌ Failed to synthesize segment {i+1} after {max_retries_per_segment} retries: {e}")
            failed_segments.append((i+1, seg_data.text, str(e)))

            # Graceful degradation: insert silence
            slot = max(10, seg_data.end_time - seg_data.start_time)
            seg = silent_segment(slot)
            print(f"   ⚠️  Inserting {slot}ms silence as fallback")

        # Crossfade append (except first segment)
        if len(timeline) > 0 and crossfade_ms > 0:
            actual_crossfade = min(crossfade_ms, len(seg) // 2)
            timeline = timeline.append(seg, crossfade=actual_crossfade)
            cursor_ms += len(seg) - actual_crossfade
        else:
            timeline += seg
            cursor_ms += len(seg)

        # Mark as completed
        completed_segments.add(segment_index)

        # Save checkpoint periodically
        if enable_checkpointing and checkpoint_path and (i + 1) % CHECKPOINT_INTERVAL == 0:
            try:
                # Save audio segments to temp files
                temp_audio_files = {}
                for idx, audio_seg in audio_segments.items():
                    temp_file = str(checkpoint_path).replace('.json', f'_seg_{idx}.wav')
                    audio_seg.export(temp_file, format="wav")
                    temp_audio_files[idx] = temp_file

                checkpoint = TTSCheckpoint(
                    task_id=task_id or "unknown",
                    total_segments=total_segments,
                    completed_segments=list(completed_segments),
                    audio_files=temp_audio_files,
                    timestamp=time.time()
                )
                checkpoint.save(str(checkpoint_path))
                print(f"💾 Checkpoint saved: {len(completed_segments)}/{total_segments} segments")
            except Exception as e:
                print(f"⚠️  Failed to save checkpoint: {e}")

        # Progress callback
        if progress_callback:
            progress_callback(len(completed_segments), total_segments)

    # Export audio
    timeline.export(output_wav, format="wav")
    print(f"✅ Export complete: {output_wav}, duration ≈ {len(timeline)/1000:.2f}s")

    # Report failed segments
    if failed_segments:
        print(f"\n⚠️  {len(failed_segments)}/{total_segments} segments failed:")
        for idx, text, error in failed_segments[:10]:  # Show first 10
            print(f"   - Segment {idx}: {text[:50]}... ({error})")
        if len(failed_segments) > 10:
            print(f"   ... and {len(failed_segments) - 10} more")

        # Save failure report
        failure_report_path = str(output_wav).replace('.wav', '_failures.txt')
        with open(failure_report_path, 'w', encoding='utf-8') as f:
            f.write(f"TTS Synthesis Failure Report\n")
            f.write(f"Total segments: {total_segments}\n")
            f.write(f"Failed segments: {len(failed_segments)}\n")
            f.write(f"Success rate: {(total_segments - len(failed_segments)) / total_segments * 100:.1f}%\n\n")
            for idx, text, error in failed_segments:
                f.write(f"Segment {idx}:\n")
                f.write(f"  Text: {text}\n")
                f.write(f"  Error: {error}\n\n")
        print(f"📄 Failure report saved: {failure_report_path}")

    # Clean up checkpoint on success
    if enable_checkpointing and checkpoint_path and os.path.exists(checkpoint_path):
        try:
            os.remove(checkpoint_path)
            # Clean up temp audio files
            for temp_file in Path(checkpoint_path).parent.glob(f"{task_id}_seg_*.wav"):
                os.remove(temp_file)
            print(f"🗑️  Checkpoint cleaned up")
        except Exception as e:
            print(f"⚠️  Failed to clean checkpoint: {e}")

    success_count = total_segments - len(failed_segments)
    return success_count, len(timeline)
