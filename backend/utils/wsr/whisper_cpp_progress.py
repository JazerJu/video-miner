"""
Whisper.cpp Real-time Progress Tracker

This module provides real-time progress tracking for whisper.cpp transcription
by parsing SRT timestamps from stdout and calculating progress percentage.

Core Mechanism:
1. Get audio total duration using ffprobe
2. Parse whisper.cpp stdout for SRT timestamps: [HH:MM:SS,mmm --> ...]
3. Convert timestamp to seconds: HH*3600 + MM*60 + SS.mmm
4. Calculate progress: (current_seconds / total_duration) * 100
5. Call progress callback with percentage updates

Author: Claude Code
Date: 2025-10-05
"""
import subprocess
import re
import json
from typing import Callable, Optional
from pathlib import Path


def get_audio_duration(audio_path: str) -> Optional[float]:
    """
    Get audio file duration in seconds using ffprobe

    Args:
        audio_path: Path to audio file

    Returns:
        Duration in seconds, or None if failed

    Example:
        >>> get_audio_duration("audio.wav")
        123.456  # 2 minutes 3.456 seconds
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            str(audio_path)
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            print(f"[whisper.cpp] ffprobe failed: {result.stderr}")
            return None

        # Parse JSON output
        data = json.loads(result.stdout)
        duration_str = data.get('format', {}).get('duration')

        if duration_str:
            duration = float(duration_str)
            print(f"[whisper.cpp] Audio duration: {duration:.2f} seconds ({duration/60:.1f} min)")
            return duration

        return None

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, json.JSONDecodeError, ValueError) as e:
        print(f"[whisper.cpp] Failed to get audio duration: {e}")
        return None


def parse_timestamp(timestamp_str: str) -> Optional[float]:
    """
    Parse SRT timestamp string to seconds

    Supports formats:
    - "00:01:23,456" (comma decimal separator)
    - "00:01:23.456" (dot decimal separator)

    Args:
        timestamp_str: Timestamp string (e.g., "00:01:23,456")

    Returns:
        Time in seconds, or None if parse failed

    Examples:
        >>> parse_timestamp("00:00:05,500")
        5.5
        >>> parse_timestamp("00:01:30.000")
        90.0
        >>> parse_timestamp("01:00:00,000")
        3600.0
    """
    try:
        # Replace comma with dot for uniform parsing
        timestamp_str = timestamp_str.replace(',', '.')

        # Split by colon: ["00", "01", "23.456"]
        parts = timestamp_str.split(':')
        if len(parts) != 3:
            return None

        hours = float(parts[0])
        minutes = float(parts[1])
        seconds = float(parts[2])

        # Calculate total seconds
        total_seconds = hours * 3600 + minutes * 60 + seconds
        return total_seconds

    except (ValueError, IndexError):
        return None


def track_whisper_progress(
    process: subprocess.Popen,
    total_duration: float,
    callback: Callable[[int, str], None],
    encoding: str = 'utf-8'
) -> str:
    """
    Track whisper.cpp progress by parsing stdout for SRT timestamps

    This function monitors whisper.cpp's stdout in real-time, looking for
    SRT timestamp lines like "[00:01:23,456 --> 00:01:25,789]". When detected,
    it extracts the start timestamp, converts it to seconds, calculates the
    progress percentage, and calls the callback function.

    Args:
        process: Running subprocess.Popen instance of whisper.cpp
        total_duration: Total audio duration in seconds
        callback: Progress callback function(percentage: int, detail: str)
        encoding: Text encoding for stdout (default: utf-8)

    Returns:
        Complete stdout output (full SRT content)

    Raises:
        RuntimeError: If whisper.cpp process fails

    Example:
        >>> process = subprocess.Popen(whisper_cmd, stdout=PIPE, stderr=PIPE, text=True)
        >>> def on_progress(percent, detail):
        ...     print(f"Progress: {percent}% - {detail}")
        >>> srt_output = track_whisper_progress(process, 600.0, on_progress)
    """
    full_output = []
    last_reported_progress = -1

    # SRT timestamp pattern: [HH:MM:SS,mmm --> HH:MM:SS,mmm]
    # Also matches with dots: [HH:MM:SS.mmm --> HH:MM:SS.mmm]
    timestamp_pattern = re.compile(r'\[(\d{2}:\d{2}:\d{2}[,.]\d{3})\s+-->')

    print(f"[whisper.cpp] Starting progress tracking (total duration: {total_duration:.1f}s)")

    try:
        while True:
            # Read line from stdout
            line = process.stdout.readline()

            # Check if process finished
            if not line:
                if process.poll() is not None:
                    # Process terminated
                    break
                continue

            full_output.append(line)

            # Look for SRT timestamp line
            match = timestamp_pattern.search(line)
            if match:
                timestamp_str = match.group(1)

                # Parse timestamp to seconds
                current_time = parse_timestamp(timestamp_str)
                if current_time is None:
                    continue

                # Calculate progress percentage (cap at 98% until completion)
                progress = int(min((current_time / total_duration) * 100, 98))

                # Only report if progress increased (avoid spam)
                if progress > last_reported_progress:
                    last_reported_progress = progress
                    detail = f"{progress}% ({current_time:.1f}s / {total_duration:.1f}s)"
                    callback(progress, detail)

                    # Debug log every 10%
                    if progress % 10 == 0:
                        print(f"[whisper.cpp] Progress: {progress}% - Timestamp: {timestamp_str}")

        # Wait for process to complete
        process.wait()

        # Check exit code
        if process.returncode != 0:
            stderr_output = process.stderr.read() if process.stderr else ""
            raise RuntimeError(
                f"whisper.cpp process failed with code {process.returncode}\n"
                f"Stderr: {stderr_output}"
            )

        # Report 100% completion
        callback(100, "Transcription completed")
        print(f"[whisper.cpp] Progress tracking completed")

        return ''.join(full_output)

    except Exception as e:
        # Ensure process is terminated
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        raise


def estimate_audio_duration(audio_path: str) -> float:
    """
    Estimate audio duration with fallback strategies

    Tries in order:
    1. ffprobe (accurate)
    2. File size estimation (approximate)
    3. Default 600 seconds (10 minutes)

    Args:
        audio_path: Path to audio file

    Returns:
        Estimated duration in seconds
    """
    # Try accurate method first
    duration = get_audio_duration(audio_path)
    if duration:
        return duration

    # Fallback: estimate from file size
    # Rough estimate: MP3 ~128kbps = 16KB/s, WAV ~1.4MB/s
    try:
        file_size = Path(audio_path).stat().st_size
        suffix = Path(audio_path).suffix.lower()

        if suffix in ['.mp3', '.m4a']:
            # Assume 128kbps MP3
            estimated_duration = file_size / (16 * 1024)
        elif suffix in ['.wav', '.flac']:
            # Assume 16-bit 44.1kHz stereo
            estimated_duration = file_size / (1.4 * 1024 * 1024)
        else:
            # Unknown format, use conservative estimate
            estimated_duration = 600

        print(f"[whisper.cpp] Estimated duration from file size: {estimated_duration:.1f}s")
        return estimated_duration

    except Exception as e:
        print(f"[whisper.cpp] Failed to estimate duration: {e}")
        # Final fallback: 10 minutes
        return 600.0
