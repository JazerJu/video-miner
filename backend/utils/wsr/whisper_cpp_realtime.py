"""
whisper.cpp 实时转录模块
独立于常规转录功能的实时转录实现
使用 --real-time 选项进行实时语音识别
"""
import subprocess
import json
import os
from typing import Callable, Optional
from pathlib import Path


def transcribe_audio_realtime(audio_file_path: str, progress_cb: Callable = None, language: str = None, model_name: str = None, use_vad: bool = True) -> str:
    """
    专为实时转录设计的whisper.cpp包装器

    支持两种模式：
    1. VAD增强模式 (默认): 使用Silero-VAD进行智能语音检测和分段
    2. 传统模式: 基于静音间隔的句子分割

    Args:
        audio_file_path: 音频文件路径
        progress_cb: 进度回调函数（可选）
        language: 语言代码
        model_name: 模型名称
        use_vad: 是否使用VAD增强模式（默认True）

    Returns:
        SRT格式字幕内容
    """
    # 获取配置
    try:
        from video.views.set_setting import load_all_settings
        settings_data = load_all_settings()
        fwsr_model = model_name or settings_data.get('Transcription Engine', {}).get('fwsr_model', 'large-v3')
        use_gpu = settings_data.get('Transcription Engine', {}).get('use_gpu', 'true').lower() in ('true', '1', 'yes')
    except:
        fwsr_model = 'large-v3'
        use_gpu = True

    # VAD增强模式 - 使用Silero-VAD进行智能分段
    if use_vad:
        try:
            print(f"[whisper.cpp-rt] Using VAD-enhanced transcription")
            from .whisper_cpp_realtime_vad import transcribe_audio_realtime_vad
            return transcribe_audio_realtime_vad(
                audio_file_path=audio_file_path,
                progress_cb=progress_cb,
                language=language,
                model_name=model_name,
                vad_threshold=0.5,  # 中等阈值，平衡精度和召回
                min_silence_duration_ms=800  # 800ms静音作为句子边界
            )
        except Exception as e:
            print(f"[whisper.cpp-rt] VAD mode failed, falling back to traditional mode: {e}")
            # 继续执行传统模式

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
    binary_path = binary_dir / 'main-vulkan'  # 直接使用vulkan版本

    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    if not binary_path.exists():
        raise FileNotFoundError(f"Binary not found: {binary_path}")

    audio_file_path_abs = str(Path(audio_file_path).resolve())

    # 构建实时转录命令 - 使用--real-time选项和JSON输出
    cmd = [
        str(binary_path),
        "-m", str(model_path),
        "-f", audio_file_path_abs,
        "--real-time",  # 启用实时转录模式
        "-oj",  # JSON输出获取词级时间戳
        "-l", language or "auto",
        "-t", "4",   # 较少线程提高实时性
        "-bs", "3",  # 较小的beam size
    ]

    print(f"[whisper.cpp-rt] Real-time transcription command: {' '.join(cmd)}")

    # 设置环境变量支持GPU库
    env = os.environ.copy()
    binary_dir_path = Path(binary_path).parent

    # Vulkan库路径
    lib_paths = []
    vulkan_lib_dirs = [
        binary_dir_path / "vulkan" / "lib",
        binary_dir_path / "lib",
    ]
    for lib_dir in vulkan_lib_dirs:
        if lib_dir.exists():
            lib_paths.append(str(lib_dir))
            print(f"[whisper.cpp-rt] 添加Vulkan库路径: {lib_dir}")

    if lib_paths:
        env["LD_LIBRARY_PATH"] = ":".join(lib_paths + [env.get("LD_LIBRARY_PATH", "")])

    # 执行转录
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', env=env)

    # 解析JSON输出
    json_file_path = Path(audio_file_path_abs + ".json")

    if result.returncode != 0:
        print(f"[whisper.cpp-rt] Warning: Process returned code {result.returncode}")
        print(f"[whisper.cpp-rt] stderr: {result.stderr[:500]}")
        if not json_file_path.exists():
            raise RuntimeError(f"whisper.cpp failed and no JSON output: {result.stderr}")
        else:
            print(f"[whisper.cpp-rt] JSON file generated despite process error")

    if not json_file_path.exists():
        raise FileNotFoundError("JSON output file not found")

    with open(json_file_path, 'r', encoding='utf-8') as f:
        transcription_data = json.load(f)

    print(f"[whisper.cpp-rt] JSON keys: {list(transcription_data.keys())}")
    if 'segments' in transcription_data:
        print(f"[whisper.cpp-rt] Number of segments: {len(transcription_data['segments'])}")
    else:
        print(f"[whisper.cpp-rt] No 'segments' key found in JSON")

    if not transcription_data.get('segments'):
        print(f"[whisper.cpp-rt] No segments found in transcription")
        return ""

    # 基于静音间隔分割句子（2秒以上静音分割）
    segments = transcription_data['segments']
    sentences = []
    current_sentence_words = []
    last_end_time = 0

    for segment in segments:
        words = segment.get('words', [])
        if not words:
            # 没有词级信息，使用整个segment
            start = segment['start']
            end = segment['end']
            text = segment['text'].strip()

            if text:
                # 检查与前一个句子的间隔
                if current_sentence_words and (start - last_end_time) > 2.0:
                    # 间隔超过2秒，结束当前句子
                    sentences.append({
                        'start': current_sentence_words[0]['start'],
                        'end': last_end_time,
                        'text': ' '.join([w['word'] for w in current_sentence_words])
                    })
                    current_sentence_words = []

                current_sentence_words.append({
                    'start': start,
                    'end': end,
                    'word': text
                })
                last_end_time = end
        else:
            # 有词级信息，逐词处理
            for word_info in words:
                word_start = word_info['start']
                word_end = word_info['end']
                word_text = word_info['word']

                # 检查静音间隔（2秒以上分割句子）
                if current_sentence_words and (word_start - last_end_time) > 2.0:
                    # 结束当前句子
                    sentences.append({
                        'start': current_sentence_words[0]['start'],
                        'end': last_end_time,
                        'text': ''.join([w['word'] for w in current_sentence_words]).strip()
                    })
                    current_sentence_words = []

                current_sentence_words.append({
                    'start': word_start,
                    'end': word_end,
                    'word': word_text
                })
                last_end_time = word_end

    # 添加最后一个句子
    if current_sentence_words:
        sentences.append({
            'start': current_sentence_words[0]['start'],
            'end': last_end_time,
            'text': ''.join([w['word'] for w in current_sentence_words]).strip()
        })

    # 生成多句SRT
    srt_lines = []
    for i, sentence in enumerate(sentences, 1):
        if sentence['text'].strip():
            start_time = _format_srt_time(sentence['start'])
            end_time = _format_srt_time(sentence['end'])
            srt_lines.append(f"{i}")
            srt_lines.append(f"{start_time} --> {end_time}")
            srt_lines.append(sentence['text'].strip())
            srt_lines.append("")  # 空行分隔

    srt_content = '\n'.join(srt_lines)
    print(f"[whisper.cpp-rt] Generated {len(sentences)} sentences from transcription")

    # 清理临时JSON文件
    try:
        json_file_path.unlink()
    except:
        pass

    return srt_content


def _format_srt_time(seconds: float) -> str:
    """将秒数转换为SRT时间格式 HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"