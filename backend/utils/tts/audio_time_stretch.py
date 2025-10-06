# -*- coding: utf-8 -*-
"""
Audio Time-Stretch Module
Provides pitch-preserving time-stretching algorithms for TTS audio adjustment

Algorithms:
- librosa: Phase vocoder (STFT-based), good for clean vocals
- rubberband: High-quality formant-preserving (requires system library)
- resample: Fallback simple resampling (changes pitch)

References:
- https://librosa.org/doc/main/generated/librosa.effects.time_stretch.html
- https://en.wikipedia.org/wiki/Audio_time_stretching_and_pitch_scaling
"""

import warnings
from typing import Optional, Literal
import numpy as np
from pydub import AudioSegment

# Algorithm availability flags
LIBROSA_AVAILABLE = False
RUBBERBAND_AVAILABLE = False

try:
    import librosa
    import soundfile as sf
    LIBROSA_AVAILABLE = True
except ImportError:
    warnings.warn("librosa not installed. Install with: pip install librosa soundfile")

try:
    import pyrubberband as pyrb
    RUBBERBAND_AVAILABLE = True
except ImportError:
    pass  # pyrubberband is optional


# ===================== Audio Conversion Utilities =====================

def audiosegment_to_numpy(audio_seg: AudioSegment) -> tuple[np.ndarray, int]:
    """
    Convert pydub AudioSegment to numpy array

    Args:
        audio_seg: Input AudioSegment

    Returns:
        Tuple of (audio_array, sample_rate)
        audio_array: shape (n_samples,) for mono, float32 in range [-1.0, 1.0]
    """
    # Get raw audio data
    samples = np.array(audio_seg.get_array_of_samples(), dtype=np.float32)

    # Normalize based on sample width
    # 16-bit: [-32768, 32767] -> [-1.0, 1.0]
    max_val = float(2 ** (8 * audio_seg.sample_width - 1))
    samples = samples / max_val

    # Handle stereo: take first channel or average
    if audio_seg.channels == 2:
        samples = samples.reshape((-1, 2))
        samples = samples[:, 0]  # Take left channel

    return samples, audio_seg.frame_rate


def numpy_to_audiosegment(audio_array: np.ndarray, sample_rate: int) -> AudioSegment:
    """
    Convert numpy array to pydub AudioSegment

    Args:
        audio_array: shape (n_samples,), float32 in range [-1.0, 1.0]
        sample_rate: Sample rate in Hz

    Returns:
        AudioSegment (16-bit mono)
    """
    # Denormalize to 16-bit int range
    samples_int16 = (audio_array * 32767).astype(np.int16)

    # Create AudioSegment
    audio_seg = AudioSegment(
        data=samples_int16.tobytes(),
        sample_width=2,  # 16-bit
        frame_rate=sample_rate,
        channels=1
    )

    return audio_seg


# ===================== Time-Stretch Algorithms =====================

def stretch_with_librosa(
    audio_array: np.ndarray,
    sample_rate: int,
    rate: float,
    quality: str = 'high'
) -> np.ndarray:
    """
    Time-stretch using librosa's phase vocoder

    Args:
        audio_array: Input audio (float32, mono)
        sample_rate: Sample rate
        rate: Stretch rate (< 1.0 = slower/longer, > 1.0 = faster/shorter)
        quality: 'low', 'medium', 'high' (affects n_fft)

    Returns:
        Stretched audio array
    """
    if not LIBROSA_AVAILABLE:
        raise ImportError("librosa is not installed")

    # Quality -> n_fft mapping
    n_fft_map = {
        'low': 512,
        'medium': 1024,
        'high': 2048
    }
    n_fft = n_fft_map.get(quality, 2048)

    # Apply time stretch
    # librosa.effects.time_stretch uses rate parameter:
    # rate > 1.0: faster (shorter duration)
    # rate < 1.0: slower (longer duration)
    stretched = librosa.effects.time_stretch(
        y=audio_array,
        rate=rate,
        n_fft=n_fft
    )

    return stretched


def stretch_with_rubberband(
    audio_array: np.ndarray,
    sample_rate: int,
    rate: float
) -> np.ndarray:
    """
    Time-stretch using Rubber Band (formant-preserving)

    Args:
        audio_array: Input audio (float32, mono)
        sample_rate: Sample rate
        rate: Stretch rate (< 1.0 = longer, > 1.0 = shorter)

    Returns:
        Stretched audio array
    """
    if not RUBBERBAND_AVAILABLE:
        raise ImportError("pyrubberband is not installed")

    # pyrubberband.time_stretch(y, sr, rate)
    # rate > 1.0: faster
    # rate < 1.0: slower
    stretched = pyrb.time_stretch(audio_array, sample_rate, rate)

    return stretched


def stretch_with_resample(
    audio_seg: AudioSegment,
    target_duration_ms: int
) -> AudioSegment:
    """
    Simple time-stretch by frame rate manipulation (changes pitch)
    This is the fallback method and will alter tone color

    Args:
        audio_seg: Input AudioSegment
        target_duration_ms: Target duration in milliseconds

    Returns:
        Resampled AudioSegment (pitch will be changed)
    """
    audio_duration_ms = len(audio_seg)
    speed_ratio = audio_duration_ms / target_duration_ms

    # Clamp to reasonable range
    speed_ratio = max(0.5, min(2.0, speed_ratio))

    original_frame_rate = audio_seg.frame_rate
    new_frame_rate = int(original_frame_rate * speed_ratio)

    adjusted_seg = audio_seg._spawn(
        audio_seg.raw_data,
        overrides={'frame_rate': new_frame_rate}
    ).set_frame_rate(original_frame_rate)

    return adjusted_seg


# ===================== Main Interface =====================

def stretch_audio(
    audio_seg: AudioSegment,
    target_duration_ms: int,
    algorithm: Literal['librosa', 'rubberband', 'resample'] = 'librosa',
    quality: str = 'high',
    max_ratio: float = 2.0,
    warn_on_extreme: bool = True
) -> AudioSegment:
    """
    Stretch audio to target duration while preserving pitch and tone color

    Args:
        audio_seg: Input AudioSegment
        target_duration_ms: Target duration in milliseconds
        algorithm: Algorithm to use ('librosa', 'rubberband', 'resample')
        quality: Quality setting for librosa ('low', 'medium', 'high')
        max_ratio: Maximum allowed stretch ratio (warning threshold)
        warn_on_extreme: Print warning if ratio exceeds max_ratio

    Returns:
        Time-stretched AudioSegment with preserved pitch

    Raises:
        ValueError: If algorithm is unavailable
    """
    current_duration_ms = len(audio_seg)

    # Calculate stretch rate
    # rate = current / target
    # rate > 1.0: speed up (make shorter)
    # rate < 1.0: slow down (make longer)
    rate = current_duration_ms / target_duration_ms

    # Check extreme ratios
    if warn_on_extreme and abs(rate - 1.0) > (max_ratio - 1.0):
        ratio_pct = abs((rate - 1.0) * 100)
        print(f"⚠️  Warning: Extreme time-stretch ratio {rate:.2f}x ({ratio_pct:.0f}% change)")
        print(f"   Audio quality may be degraded. Consider adjusting SRT timings.")

    # Algorithm selection and execution
    if algorithm == 'librosa':
        if not LIBROSA_AVAILABLE:
            print("⚠️  librosa not available, falling back to resample")
            return stretch_with_resample(audio_seg, target_duration_ms)

        try:
            audio_array, sample_rate = audiosegment_to_numpy(audio_seg)
            stretched_array = stretch_with_librosa(audio_array, sample_rate, rate, quality)
            result = numpy_to_audiosegment(stretched_array, sample_rate)
            return result
        except Exception as e:
            print(f"⚠️  librosa time-stretch failed: {e}, falling back to resample")
            return stretch_with_resample(audio_seg, target_duration_ms)

    elif algorithm == 'rubberband':
        if not RUBBERBAND_AVAILABLE:
            print("⚠️  pyrubberband not available, falling back to librosa")
            if LIBROSA_AVAILABLE:
                return stretch_audio(audio_seg, target_duration_ms, 'librosa', quality, max_ratio, False)
            else:
                return stretch_with_resample(audio_seg, target_duration_ms)

        try:
            audio_array, sample_rate = audiosegment_to_numpy(audio_seg)
            stretched_array = stretch_with_rubberband(audio_array, sample_rate, rate)
            result = numpy_to_audiosegment(stretched_array, sample_rate)
            return result
        except Exception as e:
            print(f"⚠️  rubberband time-stretch failed: {e}, falling back")
            return stretch_audio(audio_seg, target_duration_ms, 'librosa', quality, max_ratio, False)

    elif algorithm == 'resample':
        return stretch_with_resample(audio_seg, target_duration_ms)

    else:
        raise ValueError(f"Unknown algorithm: {algorithm}. Use 'librosa', 'rubberband', or 'resample'")


def get_available_algorithms() -> list[str]:
    """
    Get list of available time-stretch algorithms

    Returns:
        List of algorithm names that can be used
    """
    algos = ['resample']  # Always available

    if LIBROSA_AVAILABLE:
        algos.insert(0, 'librosa')

    if RUBBERBAND_AVAILABLE:
        algos.insert(0, 'rubberband')

    return algos


def print_algorithm_status():
    """Print availability status of all algorithms"""
    print("Time-Stretch Algorithm Availability:")
    print(f"  librosa:     {'✅ Available' if LIBROSA_AVAILABLE else '❌ Not installed'}")
    print(f"  rubberband:  {'✅ Available' if RUBBERBAND_AVAILABLE else '❌ Not installed (optional)'}")
    print(f"  resample:    ✅ Available (fallback)")
    print(f"\nRecommended: {get_available_algorithms()[0]}")


# Module initialization check
if not LIBROSA_AVAILABLE:
    print("⚠️  Warning: librosa not installed. Time-stretching will use fallback resampling method.")
    print("   Install with: pip install librosa soundfile")
