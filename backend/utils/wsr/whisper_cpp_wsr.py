"""
whisper.cpp wrapper - Drop-in replacement for fast_wsr.py
Uses official whisper.cpp binary via subprocess
Supports CPU, CUDA, and Vulkan GPU acceleration
Single-threaded for better accuracy and context preservation
Real-time progress tracking via SRT timestamp parsing
"""
import subprocess
import json
import os
import time
import random
from typing import Callable, Optional, Dict, Any
from pathlib import Path

# Import progress tracking utilities
from .whisper_cpp_progress import (
    estimate_audio_duration,
    track_whisper_progress
)


# ──────────────────────────────────────────────────────────────
# Configuration & Model Management
# ──────────────────────────────────────────────────────────────

def get_configured_model_name() -> str:
    try:
        from video.views.set_setting import load_all_settings
        settings_data = load_all_settings()
        fwsr_model = settings_data.get('Transcription Engine', {}).get('fwsr_model', 'large-v3')

        # 映射faster-whisper模型名到whisper.cpp GGML模型
        model_mapping = {
            'large-v3': 'ggml-large-v3.bin',
            'large-v2': 'ggml-large-v2.bin',
            'medium': 'ggml-medium.bin',
            'small': 'ggml-small.bin',
            'base': 'ggml-base.bin',
            'tiny': 'ggml-tiny.bin',
            'large-v3-q5': 'ggml-large-v3-q5_0.bin',
            'medium-q5': 'ggml-medium-q5_0.bin',
        }
        return model_mapping.get(fwsr_model, 'ggml-large-v3.bin')
    except:
        return 'ggml-large-v3.bin'


def get_use_gpu_setting() -> bool:
    try:
        from video.views.set_setting import load_all_settings
        settings_data = load_all_settings()
        use_gpu_str = settings_data.get('Transcription Engine', {}).get('use_gpu', 'true')
        print(f"[whisper.cpp] use_gpu setting: {use_gpu_str}")
        return use_gpu_str.lower() in ('true', '1', 'yes')
    except:
        return True  # 默认启用GPU


def _check_gpu_support(binary_path: Path) -> tuple[bool, str]:
    """
    检查whisper.cpp二进制的GPU支持类型
    返回: (支持GPU, GPU类型)  GPU类型可以是 'cuda', 'vulkan', 或 'none'
    """
    try:
        # 从文件名判断GPU类型
        binary_name = binary_path.name.lower()
        if 'vulkan' in binary_name:
            return (True, 'vulkan')
        elif 'cuda' in binary_name:
            return (True, 'cuda')
        elif 'cpu' in binary_name:
            return (False, 'none')

        # 通过ldd检查链接库
        env = os.environ.copy()
        source_dir = binary_path.parent / "source"
        lib_paths = [
            str(source_dir / "build" / "ggml" / "src" / "ggml-vulkan"),
            str(source_dir / "build" / "ggml" / "src" / "ggml-cuda"),
            str(source_dir / "build" / "ggml" / "src"),
            str(source_dir / "build" / "src"),
            "/usr/local/cuda-12.2/lib64",
        ]
        if "LD_LIBRARY_PATH" in env:
            lib_paths.append(env["LD_LIBRARY_PATH"])
        env["LD_LIBRARY_PATH"] = ":".join(lib_paths)

        result = subprocess.run(
            ['ldd', str(binary_path)],
            capture_output=True,
            text=True,
            timeout=5,
            env=env
        )
        output = result.stdout.lower()

        # 检查 Vulkan 支持
        if 'libvulkan' in output or 'ggml-vulkan' in output:
            return (True, 'vulkan')
        # 检查 CUDA 支持
        if 'libcuda' in output or 'libcublas' in output or 'ggml-cuda' in output:
            return (True, 'cuda')

        return (False, 'none')
    except:
        return (False, 'none')


def get_whisper_cpp_paths(use_gpu: bool = None) -> Dict[str, str]:
    """
    获取whisper.cpp二进制和模型路径
    根据use_gpu设置自动选择合适版本

    Args:
        use_gpu: True使用GPU版本, False使用CPU版本, None自动检测配置

    返回: {"binary": "path/to/main", "model_dir": "path/to/models", "has_cuda": bool, "gpu_type": str}
    """
    if use_gpu is None:
        use_gpu = get_use_gpu_setting()

    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent.parent
    whisper_cpp_dir = project_root / "bin" / "whisper-cpp"

    # 候选二进制列表（按优先级排序）
    candidate_bins = []
    if use_gpu:
        # GPU模式：优先Vulkan, 然后CUDA
        candidate_bins.extend([
            whisper_cpp_dir / "main-vulkan",
            whisper_cpp_dir / "main-cuda",
            whisper_cpp_dir / "vulkan" / "bin" / "whisper-cli",  # Vulkan构建输出
        ])
    # CPU作为fallback
    candidate_bins.append(whisper_cpp_dir / "main-cpu")

    # 选择二进制
    selected_bin = None
    has_cuda = False
    gpu_type = 'none'

    for bin_path in candidate_bins:
        if not bin_path.exists():
            continue

        has_gpu, detected_gpu_type = _check_gpu_support(bin_path)

        if use_gpu and has_gpu:
            # GPU模式：选择第一个支持GPU的
            selected_bin = bin_path
            has_cuda = (detected_gpu_type == 'cuda')
            gpu_type = detected_gpu_type
            print(f"[whisper.cpp] ✅ 选中GPU版本: {bin_path.name} (类型: {detected_gpu_type.upper()})")
            break
        elif not use_gpu and not has_gpu:
            # CPU模式：选择第一个不支持GPU的
            selected_bin = bin_path
            gpu_type = 'cpu'
            print(f"[whisper.cpp] ℹ️  选中CPU版本: {bin_path.name}")
            break
        elif selected_bin is None:
            # 暂存第一个可用的作为fallback
            selected_bin = bin_path
            has_cuda = (detected_gpu_type == 'cuda')
            gpu_type = detected_gpu_type

    # 验证找到的二进制
    if not selected_bin or not selected_bin.exists():
        raise FileNotFoundError(
            f"whisper.cpp binary not found!\n"
            f"Searched paths:\n" + "\n".join(f"  - {p}" for p in candidate_bins) +
            f"\n\nPlease:\n"
            f"1. Place binary at {whisper_cpp_dir}/main-cpu or main-vulkan or main-cuda\n"
            f"2. Or build from source: cd backend/bin/whisper-cpp && make\n"
            f"\nDownload from: https://github.com/ggml-org/whisper.cpp/releases"
        )

    if use_gpu and gpu_type == 'none':
        print(f"[whisper.cpp] ⚠️  GPU已启用但二进制不支持GPU，将使用CPU模式")

    # 模型目录
    model_dir = os.getenv("WHISPER_MODEL_DIR")
    if not model_dir:
        model_dir = project_root / "models"

    return {
        "binary": str(selected_bin),
        "model_dir": str(model_dir),
        "has_cuda": has_cuda,
        "gpu_type": gpu_type  # 'cuda', 'vulkan', 'cpu', 'none'
    }


# ──────────────────────────────────────────────────────────────
# Core Transcription Function
# ──────────────────────────────────────────────────────────────

def transcribe_audio(
    audio_file_path: str,
    progress_cb: Callable[[str], None],
    language: str = None
) -> str:
    """
    使用whisper.cpp转录音频文件，生成word-level时间戳的SRT字幕
    单线程处理，保持完整上下文和最佳准确性

    Args:
        audio_file_path: 音频文件路径
        progress_cb: 进度回调函数（接收字符串状态）
        language: 语言代码 (zh/en/jp/None表示自动检测)

    Returns:
        SRT格式字幕内容
    """
    progress_cb("Running")

    # 获取GPU设置
    use_gpu = get_use_gpu_setting()

    # 获取whisper.cpp路径和模型
    paths = get_whisper_cpp_paths(use_gpu=use_gpu)
    binary_path = paths["binary"]
    model_dir = Path(paths["model_dir"])
    gpu_type = paths.get("gpu_type", "none")
    model_name = get_configured_model_name()
    model_path = model_dir / model_name

    # 转换音频文件为绝对路径
    audio_file_path_abs = str(Path(audio_file_path).resolve())

    # 验证文件存在
    if not Path(binary_path).exists():
        raise FileNotFoundError(
            f"whisper.cpp binary not found at {binary_path}\n"
            f"Please install whisper.cpp binary\n"
            f"Download from: https://github.com/ggml-org/whisper.cpp/releases"
        )

    if not model_path.exists():
        raise FileNotFoundError(
            f"Model not found at {model_path}\n"
            f"Please download models using: bash backend/scripts/download_whisper_models.sh\n"
            f"Or manually from: https://huggingface.co/ggerganov/whisper.cpp/tree/main"
        )

    if not Path(audio_file_path_abs).exists():
        raise FileNotFoundError(
            f"Audio file not found at {audio_file_path_abs}\n"
            f"Original path: {audio_file_path}"
        )

    gpu_type_display = gpu_type.upper()
    print(f"[whisper.cpp] Binary: {binary_path} (GPU: {gpu_type_display})")
    print(f"[whisper.cpp] Model: {model_path}")
    print(f"[whisper.cpp] Audio: {audio_file_path_abs}")

    if use_gpu and gpu_type == 'cuda':
        print(f"[whisper.cpp] Device: 🚀 GPU (CUDA)")
    elif use_gpu and gpu_type == 'vulkan':
        print(f"[whisper.cpp] Device: 🌋 GPU (Vulkan)")
    else:
        print(f"[whisper.cpp] Device: 🐌 CPU-only")

    # 构建whisper.cpp命令
    cmd = [
        str(binary_path),
        "-m", str(model_path),
        "-f", audio_file_path_abs,
        "-ojf",  # JSON输出格式，包含word-level timestamps
        "-fa",   # 强制音频处理
        "-ml", "3",  # 最大行长度
        "--dtw", "large.v3",  # 动态时间规整
        "-t", "8",   # 8线程（CPU模式下使用）
        "-bs", "5",  # beam_size=5
        "-bo", "5",  # best_of=5
    ]

    # GPU/CPU控制 - 关键修复
    if not use_gpu or gpu_type == 'none':
        # 明确禁用GPU
        cmd.extend(["-ng"])
        print(f"[whisper.cpp] 已通过 -ng 参数禁用GPU")
    else:
        # GPU模式：whisper.cpp会自动检测并使用GPU
        print(f"[whisper.cpp] GPU模式启用 ({gpu_type})")

    # 语言参数
    if language and language != "None":
        cmd.extend(["-l", language])
        print(f"[whisper.cpp] Language: {language}")
    else:
        print(f"[whisper.cpp] Auto-detecting language")

    print(f"[whisper.cpp] Command: {' '.join(cmd)}")

    # 获取音频时长用于进度计算
    print(f"[whisper.cpp] Detecting audio duration...")
    total_duration = estimate_audio_duration(audio_file_path_abs)
    print(f"[whisper.cpp] Total duration: {total_duration:.1f}s ({total_duration/60:.1f} min)")

    # 执行whisper.cpp
    try:
        # 设置环境变量支持GPU库
        env = os.environ.copy()
        binary_dir = Path(binary_path).parent

        # 根据GPU类型设置库路径
        lib_paths = []

        if gpu_type == 'vulkan':
            # Vulkan库路径（按优先级）
            vulkan_lib_dirs = [
                binary_dir / "vulkan" / "lib",  # 标准Vulkan构建输出
                binary_dir / "lib",  # 备选lib目录
            ]
            for lib_dir in vulkan_lib_dirs:
                if lib_dir.exists():
                    lib_paths.append(str(lib_dir))
                    print(f"[whisper.cpp] 添加Vulkan库路径: {lib_dir}")

        elif gpu_type == 'cuda':
            # CUDA库路径
            cuda_lib_dirs = [
                "/usr/local/cuda-12.2/lib64",
                "/usr/local/cuda/lib64",
                binary_dir / "cuda" / "lib",
            ]
            for lib_dir in cuda_lib_dirs:
                if Path(lib_dir).exists():
                    lib_paths.append(str(lib_dir))
                    print(f"[whisper.cpp] 添加CUDA库路径: {lib_dir}")

        # 添加源码构建目录（可选）
        source_dir = binary_dir / "source"
        if source_dir.exists():
            source_lib_paths = [
                source_dir / "build" / "ggml" / "src",
                source_dir / "build" / "ggml" / "src" / "ggml-cuda",
                source_dir / "build" / "ggml" / "src" / "ggml-vulkan",
            ]
            for lib_dir in source_lib_paths:
                if lib_dir.exists():
                    lib_paths.append(str(lib_dir))

        # 保留原有的LD_LIBRARY_PATH
        if "LD_LIBRARY_PATH" in env:
            lib_paths.append(env["LD_LIBRARY_PATH"])

        # 设置环境变量
        if lib_paths:
            env["LD_LIBRARY_PATH"] = ":".join(lib_paths)
            print(f"[whisper.cpp] LD_LIBRARY_PATH: {env['LD_LIBRARY_PATH']}")
        else:
            print(f"[whisper.cpp] 使用系统默认LD_LIBRARY_PATH")

        # 启动whisper.cpp进程 (使用Popen获取实时输出)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',  # Replace invalid UTF-8 sequences
            cwd=str(Path(binary_path).parent),
            env=env
        )

        # 定义进度回调包装器
        def on_whisper_progress(percent: int, detail: str):
            """whisper.cpp进度回调: 解析时间戳后的百分比"""
            # 将百分比传递给外部回调
            progress_cb(percent)

        # 实时追踪进度并获取stdout输出
        print(f"[whisper.cpp] Starting real-time progress tracking...")
        stdout_str = track_whisper_progress(
            process=process,
            total_duration=total_duration,
            callback=on_whisper_progress,
            encoding='utf-8'
        )

        # 读取stderr
        stderr_str = process.stderr.read()

        print(f"[whisper.cpp] ✅ Transcription completed")

        # whisper.cpp 的 -oj 参数会将 JSON 写入到 <audio_file>.json 文件
        json_file_path = Path(audio_file_path_abs + ".json")

        if not json_file_path.exists():
            raise FileNotFoundError(
                f"whisper.cpp did not create JSON output file: {json_file_path}\n"
                f"stderr: {stderr_str[:200]}"
            )

        # 创建 work_dir 目录（保存JSON备份）
        work_dir = Path(__file__).resolve().parent.parent.parent / "work_dir"
        work_dir.mkdir(exist_ok=True)

        # 读取JSON文件 (whisper.cpp outputs UTF-8 text, not binary)
        # 使用 errors='replace' 处理 -ml 参数导致的UTF-8截断问题
        # 无效的UTF-8字节会被替换为 � (U+FFFD)，但顶层text字段仍然正确
        with open(json_file_path, 'r', encoding='utf-8', errors='replace') as f:
            json_str = f.read()

        # 保存备份
        timestamp = int(time.time() * 1000)
        random_suffix = random.randint(1000, 9999)
        saved_json_filename = f"whisper_cpp_{timestamp}_{random_suffix}.json"
        saved_json_path = work_dir / saved_json_filename
        with open(saved_json_path, 'w', encoding='utf-8') as f:
            f.write(json_str)
        print(f"[whisper.cpp] ✅ JSON备份已保存: {saved_json_path}")

        # 解析JSON
        transcription_data = json.loads(json_str)
        # print(f"[whisper.cpp] ✅ JSON解析成功, transcription条目数: {len(transcription_data.get('transcription', []))}")

        srt_content = _convert_whisper_cpp_to_srt(transcription_data)
        # print(f"[whisper.cpp] 成功转换为SRT, 字幕条目数: {srt_content.count('-->')}")

        # Debug: Check first 200 chars of SRT content

        # 删除whisper.cpp生成的临时JSON文件
        try:
            json_file_path.unlink()
        except Exception as e:
            print(f"[whisper.cpp] 无法删除临时JSON: {e}")

        progress_cb("Completed")
        return srt_content

    except subprocess.CalledProcessError as e:
        stderr_msg = e.stderr if isinstance(e.stderr, str) else str(e.stderr)
        print(f"[whisper.cpp] Error: {stderr_msg}")
        raise RuntimeError(f"whisper.cpp transcription failed: {stderr_msg}")
    except json.JSONDecodeError as e:
        print(f"[whisper.cpp] JSON parsing error: {e}")
        raise RuntimeError(f"Failed to parse whisper.cpp output: {e}")


# ──────────────────────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────────────────────

def _convert_whisper_cpp_to_srt(json_data: Dict[str, Any]) -> str:
    """
    将whisper.cpp的JSON输出转换为SRT字幕格式

    whisper.cpp JSON格式:
    {
      "transcription": [
        {
          "timestamps": {"from": "00:00:00,320", "to": "00:00:00,370"},
          "offsets": {"from": 320, "to": 370},
          "text": " word"
        },
        ...
      ]
    }
    """
    srt_lines = []
    index = 1

    transcription = json_data.get("transcription", [])

    for segment in transcription:
        # 只使用顶层的text字段，忽略tokens数组
        # tokens中的text可能包含 � 乱码(由于 -ml 参数截断UTF-8)
        # 但顶层text是完整正确的识别结果
        text = segment.get("text", "").strip()
        if not text:
            continue

        timestamps = segment.get("timestamps", {})
        time_from = timestamps.get("from", "00:00:00,000")
        time_to = timestamps.get("to", "00:00:00,000")

        # Write into subtitle format.
        srt_lines.append(f"{index}")
        srt_lines.append(f"{time_from} --> {time_to}")
        srt_lines.append(text)
        srt_lines.append("")

        index += 1

    return "\n".join(srt_lines)
