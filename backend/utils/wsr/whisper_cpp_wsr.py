"""
whisper.cpp wrapper - Drop-in replacement for fast_wsr.py
Uses official whisper.cpp binary via subprocess
Supports both CPU-only and CUDA GPU acceleration
"""
import subprocess
import json
import os
import shutil
import time
import random
from typing import Callable, Optional, Dict, Any
from pathlib import Path


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

        return use_gpu_str.lower() in ('true', '1', 'yes')
    except:
        return True  # 默认启用GPU


def _check_cuda_support(binary_path: Path) -> bool:
    """检查whisper.cpp二进制是否支持CUDA"""
    try:
        # 使用ldd检查是否链接了CUDA库
        result = subprocess.run(
            ['ldd', str(binary_path)],
            capture_output=True,
            text=True,
            timeout=5
        )
        output = result.stdout.lower()
        return 'libcuda' in output or 'libcublas' in output or 'ggml-cuda' in output
    except:
        return False


def get_whisper_cpp_paths(use_gpu: bool = None) -> Dict[str, str]:
    """
    获取whisper.cpp二进制和模型路径
    根据use_gpu设置自动选择CUDA或CPU版本

    Args:
        use_gpu: True使用CUDA版本, False使用CPU版本, None自动检测配置

    返回: {"binary": "path/to/main", "model_dir": "path/to/models", "has_cuda": bool}
    """
    if use_gpu is None:
        use_gpu = get_use_gpu_setting()

    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent.parent
    whisper_cpp_dir = project_root / "bin" / "whisper-cpp"

    candidate_bins = []

    # 1. 环境变量指定
    env_bin = os.getenv("WHISPER_CPP_BIN")
    if env_bin:
        candidate_bins.append(Path(env_bin))

    # 2. 项目目录中的二进制
    candidate_bins.extend([
        whisper_cpp_dir / "main-vulkan",  
        whisper_cpp_dir / "main-cuda",  # ← 添加这一行，放在最前面
        whisper_cpp_dir / "main",
        whisper_cpp_dir / "source" / "build" / "bin" / "whisper-cli",
    ])

    # 选择二进制：如果use_gpu=True，优先选择支持CUDA的版本
    selected_bin = None
    has_cuda = False

    for bin_path in candidate_bins:
        if not bin_path.exists():
            continue

        cuda_supported = _check_cuda_support(bin_path)

        if use_gpu:
            # 需要GPU：优先选择CUDA版本
            if cuda_supported:
                selected_bin = bin_path
                has_cuda = True
                print(f"[whisper.cpp] ✅ 找到CUDA版本: {bin_path}")
                break
        else:
            # CPU模式：选择第一个可用的
            selected_bin = bin_path
            has_cuda = cuda_supported
            print(f"[whisper.cpp] ℹ️ 使用二进制: {bin_path} (CUDA: {'是' if cuda_supported else '否'})")
            break

    # 如果未找到合适的二进制
    if not selected_bin:
        # 回退到默认路径
        selected_bin = whisper_cpp_dir / "main"
        if use_gpu and selected_bin.exists():
            has_cuda = _check_cuda_support(selected_bin)
            if not has_cuda:
                print(f"[whisper.cpp] ⚠️ GPU已启用但未找到CUDA编译版本，将使用CPU模式")

    # 模型目录
    model_dir = os.getenv("WHISPER_MODEL_DIR")
    if not model_dir:
        model_dir = project_root / "models"

    return {
        "binary": str(selected_bin),
        "model_dir": str(model_dir),
        "has_cuda": has_cuda
    }


# ──────────────────────────────────────────────────────────────
# Core Transcription Function
# ──────────────────────────────────────────────────────────────

def transcribe_audio(
    audio_file_path: str,
    progress_cb: Callable[[float], None],
    language: str = None
) -> str:
    """
    使用whisper.cpp转录音频文件，生成word-level时间戳的SRT字幕

    Args:
        audio_file_path: 音频文件路径
        progress_cb: 进度回调函数（接收0-100的进度或"Running"/"Completed"）
        language: 语言代码 (zh/en/jp/None表示自动检测)

    Returns:
        SRT格式字幕内容
    """
    progress_cb("Running")

    # 获取GPU设置
    use_gpu = get_use_gpu_setting()

    # 获取whisper.cpp路径和模型（根据use_gpu自动选择CUDA/CPU版本）
    paths = get_whisper_cpp_paths(use_gpu=use_gpu)
    binary_path = paths["binary"]
    model_dir = Path(paths["model_dir"])
    has_cuda = paths["has_cuda"]
    model_name = get_configured_model_name()
    model_path = model_dir / model_name

    # 如果启用GPU但没有CUDA支持，强制使用CPU
    if use_gpu and not has_cuda:
        print(f"[whisper.cpp] ⚠️ GPU已启用但二进制不支持CUDA，强制使用CPU模式")
        use_gpu = False

    # 转换音频文件为绝对路径
    audio_file_path_abs = str(Path(audio_file_path).resolve())

    # 验证文件存在
    if not Path(binary_path).exists():
        raise FileNotFoundError(
            f"whisper.cpp binary not found at {binary_path}\n"
            f"Please set WHISPER_CPP_BIN environment variable or install to backend/bin/whisper-cpp/\n"
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

    print(f"[whisper.cpp] Binary: {binary_path} (CUDA: {'✅' if has_cuda else '❌'})")
    print(f"[whisper.cpp] Model: {model_path}")
    print(f"[whisper.cpp] Audio: {audio_file_path_abs}")
    print(f"[whisper.cpp] Device: {'🚀 GPU (CUDA)' if (use_gpu and has_cuda) else '🐌 CPU-only'}")

    # 构建whisper.cpp命令
    cmd = [
        str(binary_path),
        "-m", str(model_path),
        "-f", audio_file_path_abs,  # 使用绝对路径
        "-ojf",  # JSON输出格式，包含word-level timestamps
        "-fa",
        "-ml","3",
        "--dtw","large.v3",
        "-l",language,
        "-t", "8",   # 8线程（CPU模式下使用，GPU模式下自动调整）
        # 不使用 -ml 和 -sow，让whisper.cpp输出原始word-level timestamps
        # 后续在LLM优化阶段合并成句子
    ]

    # GPU/CPU控制
    if not use_gpu:
        # 禁用GPU，强制使用CPU
        cmd.extend(["-ng"])  # --no-gpu
        print(f"[whisper.cpp] GPU disabled via -ng flag")
    else:
        # GPU模式：whisper.cpp会自动使用CUDA（如果编译时启用）
        # 注意：需要使用CUDA编译的whisper.cpp二进制
        print(f"[whisper.cpp] GPU enabled (requires CUDA-compiled binary)")

    # 语言参数
    if language and language != "None":
        cmd.extend(["-l", language])
        print(f"[whisper.cpp] Using language: {language}")
    else:
        print(f"[whisper.cpp] Auto-detecting language")

    # 其他优化参数（映射自fast_wsr.py的参数）
    cmd.extend([
        "-bs", "5",        # beam_size=5
        "-bo", "5",        # best_of=5
        # "-tr",           # translate to English (可选，默认不翻译)
    ])

    print(f"[whisper.cpp] Command: {' '.join(cmd)}")

    # 执行whisper.cpp
    try:
        # 设置环境变量以支持CUDA库
        env = os.environ.copy()
        cuda_lib_path = "/usr/local/cuda-12.2/lib64"
        source_dir = Path(binary_path).parent / "source"
        ggml_lib_paths = [
            str(source_dir / "build" / "ggml" / "src"),
            str(source_dir / "build" / "ggml" / "src" / "ggml-cuda"),
        ]

        # 构建LD_LIBRARY_PATH
        lib_paths = [cuda_lib_path] + ggml_lib_paths
        if "LD_LIBRARY_PATH" in env:
            lib_paths.append(env["LD_LIBRARY_PATH"])
        env["LD_LIBRARY_PATH"] = ":".join(lib_paths)

        # 不使用 text=True，以避免自动解码错误
        # 后续手动处理字节流
        result = subprocess.run(
            cmd,
            capture_output=True,
            check=False,  # 先不检查返回码，手动处理错误
            cwd=str(Path(binary_path).parent),  # 在二进制所在目录执行
            env=env
        )

        # 手动解码 stdout 和 stderr，使用多种编码尝试
        stdout_str = ""
        stderr_str = ""

        for encoding in ['utf-8', 'gbk', 'latin-1']:
            try:
                stdout_str = result.stdout.decode(encoding)
                stderr_str = result.stderr.decode(encoding)
                print(f"[whisper.cpp] 命令输出解码成功: {encoding}")
                break
            except UnicodeDecodeError:
                if encoding == 'latin-1':
                    # latin-1 应该总是成功
                    stdout_str = result.stdout.decode('latin-1', errors='replace')
                    stderr_str = result.stderr.decode('latin-1', errors='replace')
                    print(f"[whisper.cpp] 命令输出解码使用 latin-1 (有替换)")
                continue

        # 检查返回码
        if result.returncode != 0:
            print(f"[whisper.cpp] ❌ 命令执行失败 (返回码: {result.returncode})")
            print(f"[whisper.cpp] stdout: {stdout_str[:500]}")
            print(f"[whisper.cpp] stderr: {stderr_str[:500]}")
            raise subprocess.CalledProcessError(result.returncode, cmd, stdout_str, stderr_str)

        print(f"[whisper.cpp] ✅ Transcription completed (返回码: {result.returncode})")
        if stdout_str:
            print(f"[whisper.cpp] stdout前200字符: {stdout_str[:200]}")
        if stderr_str:
            print(f"[whisper.cpp] stderr前200字符: {stderr_str[:200]}")

        # whisper.cpp 的 -oj 参数会将 JSON 写入到 <audio_file>.json 文件
        json_file_path = Path(audio_file_path_abs + ".json")

        if not json_file_path.exists():
            raise FileNotFoundError(
                f"whisper.cpp did not create JSON output file: {json_file_path}\n"
                f"stdout: {result.stdout[:200]}\n"
                f"stderr: {result.stderr[:200]}"
            )

        # 创建 work_dir 目录（如果不存在）
        work_dir = Path(__file__).resolve().parent.parent.parent / "work_dir"
        work_dir.mkdir(exist_ok=True)

        # 生成带时间戳和随机数的文件名保存JSON
        timestamp = int(time.time() * 1000)  # 毫秒级时间戳
        random_suffix = random.randint(1000, 9999)
        saved_json_filename = f"whisper_cpp_{timestamp}_{random_suffix}.json"
        saved_json_path = work_dir / saved_json_filename

        # 读取JSON文件 - 先读取原始字节,然后尝试多种编码
        try:
            with open(json_file_path, 'rb') as f:
                raw_data = f.read()

            print(f"[whisper.cpp] JSON文件大小: {len(raw_data)} bytes")
            print(f"[whisper.cpp] 原始JSON文件路径: {json_file_path}")

            # 保存原始字节到 work_dir
            with open(saved_json_path, 'wb') as f:
                f.write(raw_data)
            print(f"[whisper.cpp] ✅ 已保存JSON到: {saved_json_path}")

            # 尝试多种编码方式解析
            json_str = None
            encoding_used = None

            # 1. 尝试UTF-8
            try:
                json_str = raw_data.decode('utf-8')
                encoding_used = 'utf-8'
                print(f"[whisper.cpp] ✅ 解码成功: UTF-8")
            except UnicodeDecodeError as e:
                print(f"[whisper.cpp] ⚠️ UTF-8解码失败: {e}")

                # 2. 尝试UTF-8-SIG (带BOM)
                try:
                    json_str = raw_data.decode('utf-8-sig')
                    encoding_used = 'utf-8-sig'
                    print(f"[whisper.cpp] ✅ 解码成功: UTF-8-SIG")
                except UnicodeDecodeError as e2:
                    print(f"[whisper.cpp] ⚠️ UTF-8-SIG解码失败: {e2}")

                    # 3. 尝试GBK (中文Windows常用编码)
                    try:
                        json_str = raw_data.decode('gbk')
                        encoding_used = 'gbk'
                        print(f"[whisper.cpp] ✅ 解码成功: GBK")
                    except UnicodeDecodeError as e3:
                        print(f"[whisper.cpp] ⚠️ GBK解码失败: {e3}")

                        # 4. 尝试替换错误字符
                        try:
                            json_str = raw_data.decode('utf-8', errors='replace')
                            encoding_used = 'utf-8 (with errors replaced)'
                            print(f"[whisper.cpp] ⚠️ UTF-8解码(替换错误): 使用�替换无效字符")
                        except Exception as e4:
                            print(f"[whisper.cpp] ⚠️ UTF-8(replace)解码失败: {e4}")

                            # 5. 最后使用latin-1作为兜底
                            json_str = raw_data.decode('latin-1')
                            encoding_used = 'latin-1 (fallback)'
                            print(f"[whisper.cpp] ⚠️ 降级到Latin-1解码")

            print(f"[whisper.cpp] 最终使用编码: {encoding_used}")
            print(f"[whisper.cpp] JSON字符串长度: {len(json_str)} chars")
            print(f"[whisper.cpp] JSON前200字符: {json_str[:200]}")

            # 解析JSON
            transcription_data = json.loads(json_str)
            print(f"[whisper.cpp] ✅ JSON解析成功, transcription条目数: {len(transcription_data.get('transcription', []))}")

        except json.JSONDecodeError as e:
            print(f"[whisper.cpp] ❌ JSON解析失败: {e}")
            print(f"[whisper.cpp] 错误位置: line={e.lineno}, column={e.colno}")
            print(f"[whisper.cpp] 已保存的JSON文件: {saved_json_path}")
            raise RuntimeError(f"Failed to parse whisper.cpp JSON output: {e}\nJSON保存在: {saved_json_path}")
        except Exception as e:
            print(f"[whisper.cpp] 读取/解析JSON时发生错误: {e}")
            print(f"[whisper.cpp] 已保存的JSON文件: {saved_json_path}")
            raise RuntimeError(f"Failed to read/parse JSON output: {e}\nJSON保存在: {saved_json_path}")

        # 转换为SRT格式
        srt_content = _convert_whisper_cpp_to_srt(transcription_data)
        print(f"[whisper.cpp] 成功转换为SRT, 字幕条目数: {srt_content.count('-->')}")

        # 删除whisper.cpp生成的临时JSON文件
        try:
            json_file_path.unlink()
            print(f"[whisper.cpp] 已删除临时JSON: {json_file_path}")
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
        # 跳过空文本和纯空格
        text = segment.get("text", "").strip()
        if not text:
            continue

        timestamps = segment.get("timestamps", {})
        time_from = timestamps.get("from", "00:00:00,000")
        time_to = timestamps.get("to", "00:00:00,000")

        # SRT格式: 序号、时间戳、文本、空行
        srt_lines.append(f"{index}")
        srt_lines.append(f"{time_from} --> {time_to}")
        srt_lines.append(text)
        srt_lines.append("")  # 空行分隔

        index += 1

    return "\n".join(srt_lines)


def _milliseconds_to_srt_time(ms: int) -> str:
    """将毫秒转换为SRT时间格式 HH:MM:SS,mmm"""
    hours = ms // 3600000
    ms %= 3600000
    minutes = ms // 60000
    ms %= 60000
    seconds = ms // 1000
    milliseconds = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


# ──────────────────────────────────────────────────────────────
# Compatibility Layer (保持与fast_wsr.py接口一致)
# ──────────────────────────────────────────────────────────────

def get_multilingual_transcription_params() -> Dict[str, Any]:
    """
    返回转录参数（兼容性函数，whisper.cpp通过命令行参数控制）
    实际参数在transcribe_audio中通过cmd构建
    """
    return {
        'language': None,
        'word_timestamps': True,  # whisper.cpp通过 -ml 1 实现
        'beam_size': 5,
        'best_of': 5,
        'temperature': [0.0, 0.2],
    }


def get_model():
    use_gpu = get_use_gpu_setting()
    paths = get_whisper_cpp_paths(use_gpu=use_gpu)
    print(f"[whisper.cpp] Model will be loaded on-demand from: {paths['model_dir']}")
    print(f"[whisper.cpp] Binary: {paths['binary']} (CUDA: {'✅' if paths['has_cuda'] else '❌'})")
    print(f"[whisper.cpp] GPU mode: {'Enabled' if use_gpu else 'Disabled (CPU-only)'}")

    if use_gpu and not paths['has_cuda']:
        print(f"[whisper.cpp] ⚠️ Warning: GPU enabled but binary doesn't support CUDA")

    return None 
