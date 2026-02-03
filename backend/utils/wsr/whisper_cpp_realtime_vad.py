"""
whisper.cpp 实时转录模块 - VAD增强版
集成 Silero-VAD 进行智能语音活动检测和分段
基于 VAD 检测的语音边界进行更准确的句子分割
"""
import subprocess
import json
import os
import tempfile
from typing import Callable, Optional, List, Dict, Any
from pathlib import Path


class VADSegment:
    """VAD检测到的语音段"""
    def __init__(self, start_ms: int, end_ms: int):
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.start_sec = start_ms / 1000.0
        self.end_sec = end_ms / 1000.0

    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec

    def __repr__(self):
        return f"VADSegment({self.start_sec:.2f}s-{self.end_sec:.2f}s, {self.duration_sec():.2f}s)"


def detect_speech_segments_vad(audio_file_path: str,
                             vad_threshold: float = 0.5,
                             min_speech_duration_ms: int = 250,
                             min_silence_duration_ms: int = 800,
                             max_speech_duration_s: float = 15.0,
                             speech_pad_ms: int = 30,
                             samples_overlap: float = 0.1,
                             use_gpu: bool = False) -> List[VADSegment]:
    """
    使用 Silero-VAD 检测语音活动分段

    Args:
        audio_file_path: 音频文件路径
        vad_threshold: VAD 阈值 (0.0-1.0)
        min_speech_duration_ms: 最短语音持续时间 (毫秒)
        min_silence_duration_ms: 最短静音持续时间 (毫秒，用于分段)
        max_speech_duration_s: 最长语音持续时间 (秒，自动分割更长的段落)
        speech_pad_ms: 语音边界填充 (毫秒)
        samples_overlap: 段间重叠时间 (秒)
        use_gpu: 是否使用GPU

    Returns:
        List[VADSegment]: 检测到的语音段列表
    """
    # 获取路径
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent.parent
    models_dir = project_root / 'models'
    binary_dir = project_root / 'bin' / 'whisper-cpp'

    vad_model_path = models_dir / 'ggml-silero-vad.bin'
    vad_binary_path = binary_dir / 'vulkan' / 'bin' / 'vad-speech-segments'

    if not vad_model_path.exists():
        raise FileNotFoundError(f"VAD model not found: {vad_model_path}")
    if not vad_binary_path.exists():
        raise FileNotFoundError(f"VAD binary not found: {vad_binary_path}")

    audio_file_path_abs = str(Path(audio_file_path).resolve())

    # 调试音频文件信息
    duration = get_audio_duration_seconds(audio_file_path_abs)
    file_size = Path(audio_file_path_abs).stat().st_size
    print(f"[VAD] Processing audio: {audio_file_path_abs}")
    print(f"[VAD] Audio info: duration={duration:.2f}s, size={file_size} bytes")

    # 构建 VAD 命令 - 使用双横线参数格式
    cmd = [
        str(vad_binary_path),
        "--file", audio_file_path_abs,
        "--vad-model", str(vad_model_path),
        "--vad-threshold", str(vad_threshold),
        "--vad-min-speech-duration-ms", str(min_speech_duration_ms),
        "--vad-min-silence-duration-ms", str(min_silence_duration_ms),
        "--vad-max-speech-duration-s", str(max_speech_duration_s),
        "--vad-speech-pad-ms", str(speech_pad_ms),
        "--vad-samples-overlap", str(samples_overlap),
        "--threads", "4",
        "--no-prints"
    ]

    # 只有在真正需要GPU时才添加（虽然通常不需要）
    if use_gpu:
        cmd.append("--use-gpu")

    # 移除空参数
    cmd = [arg for arg in cmd if arg]

    print(f"[VAD] Speech segmentation command: {' '.join(cmd)}")

    # 设置环境变量
    env = os.environ.copy()
    binary_dir_path = Path(vad_binary_path).parent

    # Vulkan库路径
    lib_paths = []
    vulkan_lib_dirs = [
        binary_dir_path / "vulkan" / "lib",
        binary_dir_path / "lib",
    ]
    for lib_dir in vulkan_lib_dirs:
        if lib_dir.exists():
            lib_paths.append(str(lib_dir))

    if lib_paths:
        env["LD_LIBRARY_PATH"] = ":".join(lib_paths + [env.get("LD_LIBRARY_PATH", "")])

    # 执行 VAD 检测
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)

    if result.returncode != 0:
        print(f"[VAD] Warning: VAD process returned code {result.returncode}")
        print(f"[VAD] stderr: {result.stderr}")
        # VAD 失败时回退到单个大段落
        return [VADSegment(0, int(get_audio_duration_seconds(audio_file_path) * 1000))]

    # 添加详细的输出调试
    print(f"[VAD] Raw VAD output (length {len(result.stdout)}):")
    print(f"[VAD] stdout: {result.stdout[:500]}{'...' if len(result.stdout) > 500 else ''}")
    if result.stderr:
        print(f"[VAD] stderr: {result.stderr[:500]}{'...' if len(result.stderr) > 500 else ''}")

    # 解析 VAD 输出 - 处理实际格式: "Speech segment 0: start = 133.00, end = 277.00"
    import re
    segments = []
    lines = result.stdout.strip().split('\n')

    # 获取音频时长用于范围验证
    duration_ms = int(get_audio_duration_seconds(audio_file_path_abs) * 1000)

    # 正则表达式匹配 VAD 输出格式 - 支持多种格式
    vad_patterns = [
        re.compile(r"Speech segment (\d+):\s*start\s*=\s*([\d.]+),\s*end\s*=\s*([\d.]+)"),
        re.compile(r"Detected (\d+) speech segments"),  # 匹配统计信息
    ]

    # 首先检查是否检测到语音段
    detected_count = 0
    for line in lines:
        line = line.strip()
        if "Detected" in line and "speech segments" in line:
            try:
                detected_count = int(line.split()[1])  # 提取数字
                print(f"[VAD] Found speech segments count: {detected_count}")
                break
            except:
                continue

    for line in lines:
        line = line.strip()
        print(f"[VAD] Processing line: '{line}'")
        if not line or line.startswith('[VAD]') or line.startswith('['):
            print(f"[VAD] Skipping line: empty or starts with bracket")
            continue

        try:
            # 尝试匹配 VAD 输出格式
            for vad_pattern in vad_patterns:
                match = vad_pattern.match(line)
                if match:
                    if vad_pattern == vad_patterns[0]:  # 语音段格式
                        segment_num = int(match.group(1))
                        start_val = float(match.group(2))
                        end_val = float(match.group(3))

                        # VAD输出的是毫秒时间，直接转换为秒
                        start_ms = int(start_val)
                        end_ms = int(end_val)
                        start_sec = start_ms / 1000.0
                        end_sec = end_ms / 1000.0
                        print(f"[VAD] Parsed VAD segment {segment_num}: {start_ms}ms-{end_ms}ms -> {start_sec:.2f}s-{end_sec:.2f}s")

                        # 确保时间段在音频范围内
                        if start_ms < duration_ms and end_ms <= duration_ms:
                            segments.append(VADSegment(start_ms, end_ms))
                            print(f"[VAD] Added valid segment: {start_ms}ms-{end_ms}ms")
                        else:
                            print(f"[VAD] Skipping out-of-range segment: {start_ms}ms-{end_ms}ms (audio duration: {duration_ms}ms)")
                    break

        except (ValueError, IndexError) as e:
            print(f"[VAD] Failed to parse line: '{line}' - {e}")
            continue

    print(f"[VAD] Detected {len(segments)} speech segments")

    # 如果没有检测到任何语音段，回退到整个音频文件
    if not segments:
        segments = [VADSegment(0, duration_ms)]
        print(f"[VAD] No speech detected, using entire audio as single segment")

    return segments


def _parse_srt_content(srt_content: str, time_offset: float) -> List[Dict[str, Any]]:
    """
    解析SRT内容并调整时间戳

    Args:
        srt_content: SRT格式的文本内容
        time_offset: 时间偏移量（秒）

    Returns:
        List[Dict]: 解析后的转录结果
    """
    entries = []
    lines = srt_content.strip().split('\n')

    i = 0
    while i < len(lines):
        # 跳过空行
        if not lines[i].strip():
            i += 1
            continue

        # 检查是否是序号
        if lines[i].strip().isdigit():
            index = int(lines[i].strip())
            i += 1

            if i >= len(lines):
                break

            # 解析时间戳行
            timestamp_line = lines[i].strip()
            i += 1

            if '-->' not in timestamp_line:
                continue

            try:
                start_str, end_str = timestamp_line.split(' --> ')
                start_time = _parse_srt_time(start_str.strip())
                end_time = _parse_srt_time(end_str.strip())

                # 收集文本行
                text_lines = []
                while i < len(lines) and lines[i].strip():
                    text_lines.append(lines[i].strip())
                    i += 1

                if text_lines:
                    text = ' '.join(text_lines)

                    # 调整时间戳
                    adjusted_entry = {
                        'start': time_offset + start_time,
                        'end': time_offset + end_time,
                        'text': text,
                        'words': []  # 简化版本，不包含词级时间戳
                    }
                    entries.append(adjusted_entry)

            except Exception as e:
                print(f"[VAD-Transcribe] Failed to parse SRT entry: {e}")
                continue

    return entries


def _parse_srt_time(time_str: str) -> float:
    """
    解析SRT时间格式为秒数

    Args:
        time_str: SRT时间格式，如 "00:00:01.234"

    Returns:
        float: 秒数
    """
    try:
        # 格式: HH:MM:SS,mmm
        parts = time_str.split(':')
        if len(parts) != 3:
            return 0.0

        hours = int(parts[0])
        minutes = int(parts[1])
        seconds_parts = parts[2].split(',')
        if len(seconds_parts) != 2:
            seconds = float(parts[2])
            milliseconds = 0
        else:
            seconds = int(seconds_parts[0])
            milliseconds = int(seconds_parts[1])

        total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
        return total_seconds

    except Exception:
        return 0.0


def transcribe_segments(audio_file_path: str,
                       segments: List[VADSegment],
                       progress_cb: Callable = None,
                       language: str = None,
                       model_name: str = None,
                       use_gpu: bool = True) -> List[Dict[str, Any]]:
    """
    转录多个VAD检测到的语音段

    Args:
        audio_file_path: 原始音频文件路径
        segments: VAD检测到的语音段列表
        progress_cb: 进度回调函数
        language: 语言代码
        model_name: 模型名称
        use_gpu: 是否使用GPU

    Returns:
        List[Dict]: 转录结果列表，每个元素包含时间戳和文本
    """
    # 获取配置
    try:
        from video.views.set_setting import load_all_settings
        settings_data = load_all_settings()
        fwsr_model = model_name or settings_data.get('Transcription Engine', {}).get('fwsr_model', 'large-v3')
    except:
        fwsr_model = 'large-v3'

    # 模型映射
    model_mapping = {
        'large-v3': 'ggml-large-v3.bin',
        'large-v2': 'ggml-large-v2.bin',
        'medium': 'ggml-medium.bin',
        'small': 'ggml-small.bin',
        'base': 'ggml-base.bin',
        'tiny': 'ggml-tiny.bin',
    }

    model_filename = model_mapping.get(fwsr_model, 'ggml-large-v3.bin')

    # 获取路径
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent.parent
    models_dir = project_root / 'models'
    binary_dir = project_root / 'bin' / 'whisper-cpp'

    model_path = models_dir / model_filename
    binary_path = binary_dir / 'main-vulkan'

    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    if not binary_path.exists():
        raise FileNotFoundError(f"Binary not found: {binary_path}")

    transcription_results = []
    total_segments = len(segments)

    # 设置环境变量
    env = os.environ.copy()
    binary_dir_path = Path(binary_path).parent
    lib_paths = []
    vulkan_lib_dirs = [
        binary_dir_path / "vulkan" / "lib",
        binary_dir_path / "lib",
    ]
    for lib_dir in vulkan_lib_dirs:
        if lib_dir.exists():
            lib_paths.append(str(lib_dir))

    if lib_paths:
        env["LD_LIBRARY_PATH"] = ":".join(lib_paths + [env.get("LD_LIBRARY_PATH", "")])

    for i, segment in enumerate(segments):
        if progress_cb:
            progress_cb(f"VAD转录进度: {i+1}/{total_segments} 段落")

        print(f"[VAD-Transcribe] Processing segment {i+1}/{total_segments}: {segment}")

        # 使用ffmpeg提取音频段
        segment_audio = extract_audio_segment(audio_file_path, segment.start_sec, segment.end_sec)
        if not segment_audio:
            print(f"[VAD-Transcribe] Failed to extract audio segment {i+1}")
            continue

        try:
            # 构建转录命令 - JSON输出格式，避免UTF-8截断
            cmd = [
                str(binary_path),
                "-m", str(model_path),
                "-f", segment_audio,
                "-ojf",  # JSON输出到文件
                "-l", language or "auto",
                "-t", "8",  # 8线程
                "-bs", "5",  # 批处理大小5
            ]

            # 注意：不添加 -ng 参数，允许使用GPU
            # 移除 -ml 参数以避免UTF-8字符截断问题

            # 执行转录
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)

            # 解析结果 - JSON文件输出
            if result.returncode != 0:
                print(f"[VAD-Transcribe] Segment {i+1} failed: {result.stderr[:200]}")
                continue

            # JSON文件输出
            json_file_path = Path(segment_audio + ".json")
            if not json_file_path.exists():
                print(f"[VAD-Transcribe] No JSON file for segment {i+1}")
                continue

            try:
                with open(json_file_path, 'r', encoding='utf-8', errors='replace') as f:
                    segment_data = json.load(f)

                # Check different possible keys for segments
                segments_key = None
                for key in ['segments', 'transcription', 'result']:
                    if key in segment_data and isinstance(segment_data[key], list):
                        segments_key = key
                        break

                # 处理转录结果
                if segments_key and segment_data.get(segments_key):
                    for raw_segment in segment_data[segments_key]:
                        # Parse timestamps from format "HH:MM:SS,mmm"
                        start_time_str = raw_segment['timestamps']['from']
                        end_time_str = raw_segment['timestamps']['to']

                        # Convert to seconds
                        start_seconds = _parse_srt_time(start_time_str.replace(',', '.'))
                        end_seconds = _parse_srt_time(end_time_str.replace(',', '.'))

                        if start_seconds is not None and end_seconds is not None:
                            # 调整时间戳到原始音频的时间轴
                            adjusted_segment = {
                                'start': segment.start_sec + start_seconds,
                                'end': segment.start_sec + end_seconds,
                                'text': raw_segment['text'].strip(),
                                'words': []
                            }

                            # 处理词级时间戳（如果有）
                            for token in raw_segment.get('tokens', []):
                                if 'timestamps' in token and token['text'].strip():
                                    token_start_str = token['timestamps']['from']
                                    token_end_str = token['timestamps']['to']

                                    token_start_sec = _parse_srt_time(token_start_str.replace(',', '.'))
                                    token_end_sec = _parse_srt_time(token_end_str.replace(',', '.'))

                                    if token_start_sec is not None and token_end_sec is not None:
                                        adjusted_word = {
                                            'start': segment.start_sec + token_start_sec,
                                            'end': segment.start_sec + token_end_sec,
                                            'word': token['text']
                                        }
                                        adjusted_segment['words'].append(adjusted_word)

                            transcription_results.append(adjusted_segment)

                print(f"[VAD-Transcribe] Segment {i+1} transcribed: {len(segment_data.get(segments_key, []))} entries")

                # 清理JSON文件
                json_file_path.unlink()

            except Exception as e:
                print(f"[VAD-Transcribe] Failed to parse JSON for segment {i+1}: {e}")
                continue

            # 清理临时音频文件
            try:
                os.unlink(segment_audio)
            except:
                pass

        except Exception as e:
            print(f"[VAD-Transcribe] Error processing segment {i+1}: {e}")
            # 清理临时文件
            try:
                os.unlink(segment_audio)
            except:
                pass

    return transcription_results


def extract_audio_segment(audio_file_path: str, start_sec: float, end_sec: float) -> Optional[str]:
    """
    使用ffmpeg提取音频片段

    Args:
        audio_file_path: 原始音频文件路径
        start_sec: 开始时间 (秒)
        end_sec: 结束时间 (秒)

    Returns:
        str: 提取的临时音频文件路径，失败时返回None
    """
    try:
        # 创建临时文件
        temp_fd, temp_path = tempfile.mkstemp(suffix='.wav')
        os.close(temp_fd)

        # 使用ffmpeg提取片段
        cmd = [
            'ffmpeg',
            '-i', audio_file_path,
            '-ss', str(start_sec),
            '-t', str(end_sec - start_sec),
            '-ac', '1',  # 单声道
            '-ar', '16000',  # 16kHz采样率
            '-loglevel', 'error',
            '-y',  # 覆盖输出文件
            temp_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            return temp_path
        else:
            print(f"[VAD] ffmpeg failed: {result.stderr}")
            try:
                os.unlink(temp_path)
            except:
                pass
            return None

    except Exception as e:
        print(f"[VAD] Failed to extract audio segment: {e}")
        return None


def get_audio_duration_seconds(audio_file_path: str) -> float:
    """
    获取音频文件时长 (秒)

    Args:
        audio_file_path: 音频文件路径

    Returns:
        float: 音频时长 (秒)
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-show_entries', 'format=duration',
            '-of', 'csv=p=0',
            audio_file_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            duration_str = result.stdout.strip()
            return float(duration_str) if duration_str else 0.0

    except Exception as e:
        print(f"[VAD] Failed to get audio duration: {e}")

    return 0.0


def transcribe_audio_simple_chunks(audio_file_path: str,
                                   progress_cb: Callable = None,
                                   language: str = None,
                                   model_name: str = None) -> str:
    """
    简化的实时转录函数 - 固定3秒+0.5秒重叠

    Args:
        audio_file_path: 音频文件路径
        progress_cb: 进度回调函数
        language: 语言代码 ('zh', 'en', 或 None 为自动检测)
        model_name: 模型名称

    Returns:
        str: SRT格式字幕内容
    """
    print(f"[Simple-Transcribe] Starting simple chunk transcription for: {audio_file_path}")

    # 获取配置
    try:
        from video.views.set_setting import load_all_settings
        settings_data = load_all_settings()
        use_gpu = settings_data.get('Transcription Engine', {}).get('use_gpu', 'true').lower() in ('true', '1', 'yes')
        fwsr_model = model_name or settings_data.get('Transcription Engine', {}).get('fwsr_model', 'large-v3')
    except:
        use_gpu = True
        fwsr_model = 'large-v3'

    # 简单参数
    CHUNK_SECONDS = 3.0      # 3秒固定块
    OVERLAP_SECONDS = 0.5    # 0.5秒重叠
    SAMPLE_RATE = 16000      # 16kHz采样率
    BYTES_PER_SAMPLE = 2     # 16位 = 2字节

    chunk_size = int(CHUNK_SECONDS * SAMPLE_RATE * BYTES_PER_SAMPLE)
    overlap_size = int(OVERLAP_SECONDS * SAMPLE_RATE * BYTES_PER_SAMPLE)

    # 获取音频时长
    total_duration = get_audio_duration_seconds(audio_file_path)
    total_chunks = int((total_duration * SAMPLE_RATE * BYTES_PER_SAMPLE - overlap_size) // (chunk_size - overlap_size)) + 1

    print(f"[Simple-Transcribe] Audio duration: {total_duration:.2f}s, chunks: {total_chunks}")

    transcription_results = []

    # 处理每个音频块
    for chunk_idx in range(total_chunks):
        if progress_cb:
            progress_cb(f"转录进度: {chunk_idx+1}/{total_chunks} 块")

        # 计算时间范围
        start_time = max(0, chunk_idx * (CHUNK_SECONDS - OVERLAP_SECONDS))
        end_time = min(total_duration, start_time + CHUNK_SECONDS)

        print(f"[Simple-Transcribe] Chunk {chunk_idx+1}: {start_time:.2f}s - {end_time:.2f}s")

        # 提取音频块
        chunk_audio = extract_audio_segment(audio_file_path, start_time, end_time)
        if not chunk_audio:
            print(f"[Simple-Transcribe] Failed to extract chunk {chunk_idx+1}")
            continue

        try:
            # 转录这个块
            chunk_result = transcribe_single_chunk(chunk_audio, fwsr_model, language, use_gpu)
            if chunk_result:
                # 调整时间戳到原始音频时间轴
                for segment in chunk_result:
                    segment['start'] += start_time
                    segment['end'] += start_time
                transcription_results.extend(chunk_result)
                print(f"[Simple-Transcribe] Chunk {chunk_idx+1} transcribed: {len(chunk_result)} segments")

            # 清理临时文件
            try:
                os.unlink(chunk_audio)
            except:
                pass

        except Exception as e:
            print(f"[Simple-Transcribe] Error processing chunk {chunk_idx+1}: {e}")
            try:
                os.unlink(chunk_audio)
            except:
                pass

    print(f"[Simple-Transcribe] Total transcribed segments: {len(transcription_results)}")

    # 生成SRT
    srt_content = generate_simple_srt(transcription_results)
    print(f"[Simple-Transcribe] Generated SRT")

    return srt_content


def transcribe_single_chunk(audio_file_path: str, model_name: str, language: str, use_gpu: bool) -> List[Dict[str, Any]]:
    """转录单个音频块"""
    # 模型映射
    model_mapping = {
        'large-v3': 'ggml-large-v3.bin',
        'large-v2': 'ggml-large-v2.bin',
        'medium': 'ggml-medium.bin',
        'small': 'ggml-small.bin',
        'base': 'ggml-base.bin',
        'tiny': 'ggml-tiny.bin',
    }

    model_filename = model_mapping.get(model_name, 'ggml-large-v3.bin')

    # 获取路径
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent.parent
    models_dir = project_root / 'models'
    binary_dir = project_root / 'bin' / 'whisper-cpp'

    model_path = models_dir / model_filename
    binary_path = binary_dir / 'main-vulkan'

    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    if not binary_path.exists():
        raise FileNotFoundError(f"Binary not found: {binary_path}")

    # 环境变量
    env = os.environ.copy()
    binary_dir_path = Path(binary_path).parent
    lib_paths = []
    vulkan_lib_dirs = [
        binary_dir_path / "vulkan" / "lib",
        binary_dir_path / "lib",
    ]
    for lib_dir in vulkan_lib_dirs:
        if lib_dir.exists():
            lib_paths.append(str(lib_dir))

    if lib_paths:
        env["LD_LIBRARY_PATH"] = ":".join(lib_paths + [env.get("LD_LIBRARY_PATH", "")])

    # 构建命令
    cmd = [
        str(binary_path),
        "-m", str(model_path),
        "-f", audio_file_path,
        "-ojf",  # JSON输出到文件
        "-l", language or "auto",
        "-t", "8",
        "-bs", "5",
    ]

    # 执行转录
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)

    if result.returncode != 0:
        print(f"[Simple-Transcribe] Transcription failed: {result.stderr[:200]}")
        return []

    # 解析JSON结果
    json_file_path = Path(audio_file_path + ".json")
    if not json_file_path.exists():
        print(f"[Simple-Transcribe] No JSON file found")
        return []

    try:
        with open(json_file_path, 'r', encoding='utf-8', errors='replace') as f:
            data = json.load(f)

        segments_key = None
        for key in ['segments', 'transcription', 'result']:
            if key in data and isinstance(data[key], list):
                segments_key = key
                break

        results = []
        if segments_key and data.get(segments_key):
            for segment in data[segments_key]:
                start_time_str = segment['timestamps']['from']
                end_time_str = segment['timestamps']['to']

                start_seconds = _parse_srt_time(start_time_str.replace(',', '.'))
                end_seconds = _parse_srt_time(end_time_str.replace(',', '.'))

                if start_seconds is not None and end_seconds is not None:
                    results.append({
                        'start': start_seconds,
                        'end': end_seconds,
                        'text': segment['text'].strip(),
                        'words': []
                    })

        # 清理JSON文件
        json_file_path.unlink()
        return results

    except Exception as e:
        print(f"[Simple-Transcribe] Failed to parse JSON: {e}")
        try:
            json_file_path.unlink()
        except:
            pass
        return []


def generate_simple_srt(transcription_results: List[Dict[str, Any]]) -> str:
    """生成简化的SRT格式"""
    srt_lines = []

    for i, segment in enumerate(transcription_results, 1):
        if segment['text'].strip():
            start_time = _format_srt_time(segment['start'])
            end_time = _format_srt_time(segment['end'])

            srt_lines.append(f"{i}")
            srt_lines.append(f"{start_time} --> {end_time}")
            srt_lines.append(segment['text'].strip())
            srt_lines.append("")

    return '\n'.join(srt_lines)


def transcribe_audio_realtime_vad(audio_file_path: str,
                                 progress_cb: Callable = None,
                                 language: str = None,
                                 model_name: str = None,
                                 vad_threshold: float = 0.5,
                                 min_silence_duration_ms: int = 800) -> str:
    """
    VAD增强的实时转录函数

    使用 Silero-VAD 进行智能语音检测，基于真实的语音边界进行转录

    Args:
        audio_file_path: 音频文件路径
        progress_cb: 进度回调函数
        language: 语言代码 ('zh', 'en', 或 None 为自动检测)
        model_name: 模型名称
        vad_threshold: VAD 阈值 (0.0-1.0，越高越严格)
        min_silence_duration_ms: 最小静音时长 (毫秒，用于句子分割)

    Returns:
        str: SRT格式字幕内容
    """
    print(f"[VAD-Realtime] Starting VAD-enhanced transcription for: {audio_file_path}")
    print(f"[VAD-Realtime] Parameters: threshold={vad_threshold}, min_silence={min_silence_duration_ms}ms")

    # 获取配置
    try:
        from video.views.set_setting import load_all_settings
        settings_data = load_all_settings()
        use_gpu = settings_data.get('Transcription Engine', {}).get('use_gpu', 'true').lower() in ('true', '1', 'yes')
    except:
        use_gpu = True

    try:
        # 第一步：VAD语音检测
        if progress_cb:
            progress_cb("VAD语音检测中...")

        vad_segments = detect_speech_segments_vad(
            audio_file_path=audio_file_path,
            vad_threshold=0.3,  # 降低阈值，更敏感
            min_speech_duration_ms=100,  # 降低最小语音时长
            min_silence_duration_ms=400,  # 降低静音检测时长
            max_speech_duration_s=30.0,  # 增加最大段落长度
            speech_pad_ms=30,  # 减少填充
            samples_overlap=0.1,  # 减少重叠
            use_gpu=False  # VAD doesn't need GPU
        )

        print(f"[VAD-Realtime] VAD detected {len(vad_segments)} speech segments")

        # 第二步：转录每个语音段
        if progress_cb:
            progress_cb(f"开始转录 {len(vad_segments)} 个语音段...")

        transcription_results = transcribe_segments(
            audio_file_path=audio_file_path,
            segments=vad_segments,
            progress_cb=progress_cb,
            language=language,
            model_name=model_name,
            use_gpu=use_gpu
        )

        print(f"[VAD-Realtime] Transcribed {len(transcription_results)} segments")

        # 第三步：生成SRT格式
        if progress_cb:
            progress_cb("生成字幕格式...")

        srt_content = generate_vad_based_srt(transcription_results)

        print(f"[VAD-Realtime] Generated SRT with {len(srt_content.split(chr(10)))//4} subtitle entries")

        return srt_content

    except Exception as e:
        print(f"[VAD-Realtime] Error during VAD transcription: {e}")
        # 回退到原始方法
        print(f"[VAD-Realtime] Falling back to original method...")
        from .whisper_cpp_realtime import transcribe_audio_realtime
        return transcribe_audio_realtime(audio_file_path, progress_cb, language, model_name)


def generate_vad_based_srt(transcription_results: List[Dict[str, Any]]) -> str:
    """
    基于VAD检测结果生成SRT字幕

    Args:
        transcription_results: 转录结果列表

    Returns:
        str: SRT格式字幕
    """
    srt_lines = []

    for i, segment in enumerate(transcription_results, 1):
        if segment['text'].strip():
            start_time = _format_srt_time(segment['start'])
            end_time = _format_srt_time(segment['end'])

            srt_lines.append(f"{i}")
            srt_lines.append(f"{start_time} --> {end_time}")
            srt_lines.append(segment['text'].strip())
            srt_lines.append("")  # 空行分隔

    return '\n'.join(srt_lines)


def _format_srt_time(seconds: float) -> str:
    """将秒数转换为SRT时间格式 HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
