"""
Standalone audio and media processing utilities (FFmpeg/ffprobe wrappers, extraction, format checks).
"""
import os
import json
import subprocess
from pathlib import Path

from django.conf import settings

from ..models import Video


def is_audio_file(filename: str) -> bool:
    """Check if a filename has an audio file extension"""
    if not filename:
        return False
    audio_extensions = ['.mp3', '.m4a', '.aac', '.wav', '.flac', '.alac']
    return os.path.splitext(filename)[1].lower() in audio_extensions


def get_media_path_info(filename: str) -> tuple[str, str]:
    """
    Get the appropriate directory and URL prefix for a media file
    Returns: (directory_name, url_prefix)
    """
    if is_audio_file(filename):
        return 'saved_audio', 'audio'
    return 'saved_video', 'video'


def has_waveform_peaks(video_filename: str) -> tuple[bool, str]:
    """
    Check if a waveform (.peaks.json) exists for the given video filename
    Returns: (exists, full_path)
    """
    if not video_filename:
        return False, ''
    base = os.path.splitext(video_filename)[0]
    path = os.path.join(settings.MEDIA_ROOT, 'waveform_data', f"{base}.peaks.json")
    return (os.path.exists(path), path)


def detect_video_audio_format(video_path: str) -> str:
    """
    Detect the original audio codec in a video file and map to extension
    """
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_streams', '-select_streams', 'a:0', video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            streams = data.get('streams') or []
            if streams:
                codec = streams[0].get('codec_name', '')
                mapping = {
                    'opus': 'opus', 'aac': 'aac', 'mp3': 'mp3',
                    'vorbis': 'ogg', 'flac': 'flac', 'pcm_s16le': 'wav',
                    'ac-3': 'ac3', 'eac3': 'eac3'
                }
                return mapping.get(codec, 'aac')
    except Exception:
        pass
    return 'aac'


def extract_audio_from_video_file(
    video_path: str, audio_path: str, preserve_format: bool = True
) -> tuple[bool, str | None, int]:
    """
    Extract audio from a video into audio_path.
    preserve_format=True copies the original stream; otherwise transcodes.
    Returns: (success, error_message_or_None, size_bytes)
    """
    if preserve_format:
        cmd = ['ffmpeg', '-i', video_path, '-vn', '-acodec', 'copy', '-y', audio_path]
    else:
        ext = os.path.splitext(audio_path)[1].lstrip('.')
        codec = 'aac'
        if ext == 'mp3': codec = 'mp3'
        elif ext == 'alac': codec = 'alac'
        elif ext == 'flac': codec = 'flac'
        elif ext == 'wav': codec = 'pcm_s16le'
        cmd = [
            'ffmpeg', '-i', video_path, '-vn', '-acodec', codec,
            '-ab', '192k', '-ar', '44100', '-y', audio_path
        ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0 and os.path.exists(audio_path):
            size = os.path.getsize(audio_path)
            return True, None, size
        if os.path.exists(audio_path): os.remove(audio_path)
        return False, result.stderr, 0
    except subprocess.TimeoutExpired:
        return False, 'timeout', 0
    except Exception as e:
        return False, str(e), 0


def get_audio_file_for_transcription(video_id: int) -> tuple[str, bool]:
    """
    Ensure an audio file exists for transcription, extracting if needed.
    Returns: (audio_path, was_extracted)
    """
    video, file_path, audio_dir = get_video_file_paths(video_id)
    if is_audio_file(video.url):
        if os.path.exists(file_path):
            return file_path, False
        # Fallback: some audio files were saved into saved_video/ by mistake
        # (legacy uploads before handle_upload routed by file type)
        fallback = os.path.join(settings.MEDIA_ROOT, 'saved_video', video.url)
        if os.path.exists(fallback):
            return fallback, False
        raise FileNotFoundError(file_path)
    base = os.path.splitext(video.url)[0]
    for ext in ['.mp3', '.wav', '.m4a', '.aac']:
        p = os.path.join(audio_dir, f"{base}{ext}")
        if os.path.exists(p):
            return p, False
    os.makedirs(audio_dir, exist_ok=True)
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)
    fmt = detect_video_audio_format(file_path)
    audio_path = os.path.join(audio_dir, f"{base}.{fmt}")
    ok, err, _ = extract_audio_from_video_file(file_path, audio_path, True)
    if ok:
        return audio_path, True
    raise RuntimeError(err or 'extraction failed')


def get_transcription_audio_path(video_id: int) -> str:
    """
    Simplified interface for transcription audio path.
    """
    path, _ = get_audio_file_for_transcription(video_id)
    return path

def is_hls_compatible(video_path: str) -> tuple[bool, str]:
    """
    Check if a video file is HLS-compatible (H264/H265 + AAC/MP3/AC3).
    Returns: (ok, message)
    """
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', video_path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            return False, res.stderr
        info = json.loads(res.stdout)
        vcodec = acodec = None
        for s in info.get('streams', []):
            if s.get('codec_type') == 'video' and not vcodec:
                vcodec = s.get('codec_name')
            if s.get('codec_type') == 'audio' and not acodec:
                acodec = s.get('codec_name')
        okv = vcodec in ('h264','hevc','h265')
        oka = not acodec or acodec in ('aac','mp3','ac3')
        if not okv: return False, f"video: {vcodec}"
        if not oka: return False, f"audio: {acodec}"
        return True, 'ok'
    except Exception as e:
        return False, str(e)


def extract_hls_from_video_file(video_path: str) -> tuple[bool, str, str]:
    """
    Generate HLS segments and playlist for a compatible video file.
    Returns: (success, error_or_empty, rel_dir)
    """
    if not os.path.exists(video_path):
        return False, 'not found', ''
    name = Path(video_path).stem
    ok, msg = is_hls_compatible(video_path)
    if not ok:
        return False, msg, ''
    out = os.path.join(settings.MEDIA_ROOT, 'stream_video', name)
    os.makedirs(out, exist_ok=True)
    playlist = os.path.join(out, 'index.m3u8')
    cmd = ['ffmpeg', '-i', video_path, '-c:v', 'copy', '-c:a', 'copy',
           '-hls_time', '10', '-hls_list_size', '0', '-hls_segment_filename',
           os.path.join(out, 'seg%d.ts'), playlist]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if res.returncode == 0 and os.path.exists(playlist):
            return True, '', f"stream_video/{name}"
        return False, res.stderr, ''
    except Exception as e:
        return False, str(e), ''

def get_video_file_paths(video_id: int) -> tuple[Video, str, str]:
    """
    Return (Video instance, absolute media path, absolute audio dir) for a video_id.
    """
    video = Video.objects.get(pk=video_id)
    dir_name, _ = get_media_path_info(video.url)
    media = os.path.join(settings.MEDIA_ROOT, dir_name)
    return video, os.path.join(media, video.url), os.path.join(settings.MEDIA_ROOT, 'saved_audio')
