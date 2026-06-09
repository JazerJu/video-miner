from django.views import View
import os, time, configparser
from queue import Queue, Empty
from collections import defaultdict
from django.http import JsonResponse
from django.db import transaction
from .models import Video
from utils.split_subtitle.main import optimise_srt
from django.conf import settings  # 确保这个在顶部
import hashlib
from .views.set_setting import load_all_settings
import logging
logger = logging.getLogger("video.tasks")

"""
该文件用于定义和 存储项目的 所有task，
包括字幕撰写/翻译；
视频下载/音视频合成；
的所有项目字段。
"""

"""
字幕生成流程：

1.生成字级时间戳的字幕，
2.大语言模型优化。
3.如果选项为翻译，翻译成对应语言。
一共有这样四个状态： Queued / Running / Completed / Failed
"""

subtitle_task_queue: Queue[str] = (
    Queue()
)  # 改为 str 类型，支持 video_id 和 external_task_id
download_queue: Queue[int] = Queue()
SAVE_DIR = "media/saved_srt"

# 线程锁保护 download_status 的并发访问
import threading

download_status_lock = threading.RLock()

# 外部转录任务状态跟踪
external_task_status = defaultdict(
    lambda: {
        "task_id": "",
        "filename": "",
        "audio_file_path": "",
        "task_type": "external",  # 标识为外部任务
        "created_at": 0,
        "status": "Queued",  # 队列中、运行中、已完成、失败
        "result_file": "",
        "error_message": "",
    }
)

# 🆕 实时字幕流状态跟踪（sentence-by-sentence）
realtime_subtitle_status = defaultdict(
    lambda: {
        "task_id": "",
        "video_id": 0,
        "filename": "",
        "status": "Queued",  # Queued/Running/Completed/Failed
        "total_entries": 0,
        "completed_entries": 0,
        "current_entry": None,  # 当前处理的字幕条目
        "subtitle_entries": [],  # 已完成的字幕条目列表
        "error_message": "",
        "created_at": 0,
    }
)

# 每个 video_id 对应 3 个阶段
# stages = 0: 字级时间戳 1: 大模型优化 2: 翻译
subtitle_task_status = defaultdict(
    lambda: {
        "filename": "",
        "src_lang": "None",
        "trans_lang": "None",  # 要翻译成的语言 None(表示不翻译),zh,en,jp
        "video_id": 0,
        "stages": {
            "transcribe": "Queued",
            "optimize": "Queued",
            "translate": "Queued",
        },
        # 🆕 进度追踪系统
        "stage_progress": {  # 各阶段进度百分比 (0-100)
            "transcribe": 0,
            "optimize": 0,
            "translate": 0,
        },
        "stage_detail": {  # 各阶段详细进度信息
            "transcribe": "",
            "optimize": "",
            "translate": "",
        },
        "stage_weights": {  # 各阶段权重（40:30:30）
            "transcribe": 0.40,  # 字幕生成占40%
            "optimize": 0.30,  # 字幕优化占30%
            "translate": 0.30,  # 翻译占30%
        },
        "total_progress": 0,  # 总进度百分比 (0-100)
        "optimize_total_chunks": 0,  # 优化任务总chunk数
        "optimize_completed_chunks": 0,  # 优化已完成chunk数
        "translate_total_chunks": 0,  # 翻译任务总chunk数
        "translate_completed_chunks": 0,  # 翻译已完成chunk数
    }
)
FIXED_NUM_THREADS = 8


def _get_thread_count(purpose: str) -> int:
    """Read thread count from config, fallback to FIXED_NUM_THREADS."""
    try:
        settings_data = load_all_settings()
        key = f"{purpose}_num_threads"
        val = settings_data.get("DEFAULT", {}).get(key, str(FIXED_NUM_THREADS))
        return max(1, min(32, int(val)))
    except Exception:
        return FIXED_NUM_THREADS

# subtitle_task_status[20000]={
#     "filename": "A default subtitle task",
#     "src_lang": "en",
#     "trans_lang": "None",  # Language to be translated into None(means no translation),zh,en,jp.
#     "video_id": 20000,
#     "stages": {
#         "transcribe":  "Queued",
#         "optimize":    "Queued",
#         "translate":   "Queued",
#     },
#     }


# 更新任务列表中对应video id的字幕生成任务status
def _update(
    video_id: int, stage: str, status: str, progress: int = None, detail: str = None
):
    """
    更新字幕任务的阶段状态和进度

    Args:
        video_id: 视频ID
        stage: 阶段名称 (transcribe/optimize/translate)
        status: 状态 (Queued/Running/Completed/Failed)
        progress: 该阶段进度百分比 (0-100)，可选
        detail: 详细进度信息（如"Segment 2/6 (33%)"），可选
    """
    task = subtitle_task_status.get(video_id)
    if task is None:
        return
    if stage not in task["stages"]:
        return
    task["stages"][stage] = status

    # 更新详细进度信息
    if detail is not None:
        if "stage_detail" not in task:
            task["stage_detail"] = {}
        task["stage_detail"][stage] = detail

    # 更新阶段进度
    if progress is not None:
        clamped = min(100, max(0, progress))
        if status == "Running":
            task["stage_progress"][stage] = max(task["stage_progress"][stage], clamped)
        else:
            task["stage_progress"][stage] = clamped
    elif status == "Completed":
        task["stage_progress"][stage] = 100
    elif status == "Running" and task["stage_progress"][stage] == 0:
        task["stage_progress"][stage] = (
            2.5  # Running时至少显示2.5% (权重0.4时总进度为1%)
        )

    # 🆕 计算总进度
    total = sum(
        task["stage_weights"][s] * task["stage_progress"][s]
        for s in task["stage_progress"]
    )
    task["total_progress"] = round(total, 1)


def preprocess_audio_for_transcription(video_id):
    """
    预处理音频文件：转换为单声道MP3格式，优化转录效果
    返回: preprocessed_audio_path (string)
    """
    import subprocess
    import os
    from .views.videos import get_transcription_audio_path

    # 获取原始音频文件路径
    original_audio_path = get_transcription_audio_path(video_id)

    # 创建临时音频目录
    temp_audio_dir = "work_dir/temp_audio"
    os.makedirs(temp_audio_dir, exist_ok=True)

    # 生成预处理后的音频文件路径
    preprocessed_audio_path = os.path.join(temp_audio_dir, f"{video_id}.mp3")

    # 检查是否已经存在预处理后的文件
    if os.path.exists(preprocessed_audio_path):
        logger.info("Preprocessed audio already exists: %s", preprocessed_audio_path)
        return preprocessed_audio_path

    logger.info("Preprocessing audio: %s -> %s", original_audio_path, preprocessed_audio_path)

    # 使用FFmpeg转换为单声道MP3格式
    ffmpeg_cmd = [
        "ffmpeg",
        "-i",
        original_audio_path,
        "-ac",
        "1",  # 转换为单声道
        "-ar",
        "16000",  # 设置采样率为16kHz (Whisper推荐)
        "-ab",
        "128k",  # 音频比特率128k (平衡质量和大小)
        "-acodec",
        "mp3",  # 使用MP3编码器
        "-y",  # 覆盖输出文件
        preprocessed_audio_path,
    ]

    try:
        logger.debug("FFmpeg command: %s", ' '.join(ffmpeg_cmd))
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5分钟超时
        )

        if result.returncode == 0 and os.path.exists(preprocessed_audio_path):
            audio_size = os.path.getsize(preprocessed_audio_path)
            logger.info(
                "Audio preprocessing successful: %s (%s bytes)", preprocessed_audio_path, audio_size
            )
            return preprocessed_audio_path
        else:
            logger.error("FFmpeg preprocessing failed: %s", result.stderr)
            raise Exception(f"Audio preprocessing failed: {result.stderr}")

    except subprocess.TimeoutExpired:
        raise Exception("Audio preprocessing timed out")
    except Exception as e:
        raise Exception(f"Audio preprocessing error: {str(e)}")


def handle_translation_only(
    video_id: int, video, src_lang: str, trans_lang: str, emphasize_dst: str = ""
) -> None:
    """处理仅翻译模式的字幕任务"""
    try:
        # 获取视频的原始语言，如果没有设置则使用src_lang
        original_lang = video.raw_lang or src_lang
        if original_lang == "existing":
            # 查找已有的字幕文件
            original_lang = video.raw_lang or "en"  # 默认为英文

        # 查找原文字幕文件
        original_srt_name = f"{video_id}_{original_lang}.srt"
        original_srt_path = os.path.join(SAVE_DIR, original_srt_name)

        if not os.path.exists(original_srt_path):
            # 如果找不到指定语言的字幕，尝试查找任何已有的字幕文件
            for lang in ["en", "zh", "jp", "de"]:
                alt_srt_name = f"{video_id}_{lang}.srt"
                alt_srt_path = os.path.join(SAVE_DIR, alt_srt_name)
                if os.path.exists(alt_srt_path):
                    original_srt_path = alt_srt_path
                    original_lang = lang
                    break
            else:
                raise Exception(
                    f"Original subtitle file not found for video {video_id}. Please generate original subtitles first."
                )

        logger.info("Using original subtitle file: %s", original_srt_path)

        # 设置翻译字幕路径
        translated_srt_name = f"{video_id}_{trans_lang}.srt"
        translated_srt_path = os.path.join(SAVE_DIR, translated_srt_name)

        # 执行翻译
        _update(video_id, "translate", "Running")
        from utils.split_subtitle.main import translate_srt

        translate_srt(
            raw_srt_path=original_srt_path,
            translate_srt_path=translated_srt_path,
            raw_lang=original_lang,
            target_lang=trans_lang,
            use_translation_cache=True,
            num_threads=_get_thread_count("translate"),
            progress_cb=lambda status: _update(video_id, "translate", status),
            terms_to_note=emphasize_dst,
        )
        _update(video_id, "translate", "Completed")

        # 更新数据库 - 只更新翻译字幕路径
        with transaction.atomic():
            video.translated_srt_path = translated_srt_name
            video.save(update_fields=["translated_srt_path"])

        logger.info(
            "Translation completed for video %s: %s -> %s", video_id, original_lang, trans_lang
        )

    except Exception as exc:
        logger.error("Translation-only failed for video %s: %s", video_id, exc)
        _update(video_id, "translate", "Failed")
        raise exc


def generate_external_transcription(task_id: str) -> None:
    """处理外部转录任务，只输出字级时间戳字幕"""
    task = external_task_status[task_id]

    try:
        task["status"] = "Running"
        audio_file_path = task["audio_file_path"]

        logger.info("Starting external transcription for task %s: %s", task_id, task['filename'])

        from asr_utils.transcription_engine import (
            transcribe_with_engine,
            load_transcription_settings,
        )

        settings = load_transcription_settings()
        transcription_settings = settings.get("Transcription Engine", {})
        primary_engine = transcription_settings.get("primary_engine", "funasr_gguf")
        fallback_engine = transcription_settings.get("fallback_engine", "")

        def progress_cb(status):
            logger.debug("External task %s progress: %s", task_id, status)

        logger.info(
            "Using primary '%s' (fallback: '%s') for external task %s",
            primary_engine, fallback_engine, task_id
        )
        srt_content = transcribe_with_engine(
            engine_type=primary_engine,
            audio_file_path=audio_file_path,
            progress_cb=progress_cb,
            fallback_engine=fallback_engine,
        )

        # 保存结果文件
        external_result_dir = "work_dir/external_results"
        os.makedirs(external_result_dir, exist_ok=True)
        result_file = os.path.join(external_result_dir, f"{task_id}.srt")

        with open(result_file, "w", encoding="utf-8") as f:
            f.write(srt_content)

        # 更新任务状态
        task["status"] = "Completed"
        task["result_file"] = result_file

        logger.info("External transcription completed for task %s", task_id)

    except Exception as exc:
        logger.error("External transcription failed for task %s: %s", task_id, exc)
        task["status"] = "Failed"
        task["error_message"] = str(exc)


def generate_subtitles_for_video(video_id: int) -> None:
    """内部字幕生成，字幕生成中真正干活的函数,也是每个video_id的Task在做的事"""
    task = subtitle_task_status[video_id]

    video = Video.objects.get(pk=video_id)
    filename, src_lang, trans_lang = (
        task["filename"],
        task["src_lang"],
        task["trans_lang"],
    )
    logger.info("filename=%s, src_lang=%s, trans_lang=%s", filename, src_lang, trans_lang)
    emphasize_dst = task.get("emphasize_dst", "")  # 获取术语信息
    translation_only = task.get("translation_only", False)  # 检查是否为仅翻译模式

    if not video:
        raise Exception("Video not found")
    video_path = video.url

    # 检查是否为仅翻译模式
    if translation_only:
        logger.info("Translation-only mode for video %s", video_id)
        # 跳过转录和优化阶段，直接处理翻译
        _update(video_id, "transcribe", "Skipped")
        _update(video_id, "optimize", "Skipped")

        # 执行翻译
        handle_translation_only(video_id, video, src_lang, trans_lang, emphasize_dst)
        return

    # 1. 音频转录阶段
    def transcribe_cb(status):
        """
        处理转录进度回调
        status可能是:
        - 整数百分比: 0-100 (whisper.cpp实时进度)
        - 字符串状态: "Running", "Completed", "Failed"
        - 段级进度: "Segment 2/6 (33%)"
        """
        import re

        # 检查是否为整数百分比 (whisper.cpp实时进度)
        if isinstance(status, (int, float)):
            _update(
                video_id,
                "transcribe",
                "Running",
                progress=int(status),
                detail=f"{int(status)}% transcribing...",
            )
        # 检查是否为段级进度信息
        elif isinstance(status, str):
            segment_match = re.match(r"Segment (\d+)/(\d+) \((\d+)%\)", status)
            if segment_match:
                completed, total, percent = segment_match.groups()
                _update(
                    video_id,
                    "transcribe",
                    "Running",
                    progress=int(percent),
                    detail=status,
                )
            else:
                # 普通状态字符串
                _update(video_id, "transcribe", status)

    logger.info("start transcribing: %s", video_path)

    try:
        _update(video_id, "transcribe", "Running")

        # 预处理音频文件：转换为单声道MP3格式
        preprocessed_audio_path = preprocess_audio_for_transcription(video_id)
        logger.info("Transcribing preprocessed audio file: %s", preprocessed_audio_path)

        # 使用统一的转录引擎接口
        from asr_utils.transcription_engine import (
            transcribe_with_engine,
            load_transcription_settings,
        )

        # 加载转录引擎配置
        settings = load_transcription_settings()
        transcription_settings = settings.get("Transcription Engine", {})
        default_settings = settings.get("DEFAULT", {})

        primary_engine = transcription_settings.get("primary_engine", "funasr_gguf")
        fallback_engine = transcription_settings.get("fallback_engine", "")
        enable_split = default_settings.get("enable_split", "true").lower() == "true"

        logger.info("Using primary transcription engine: %s", primary_engine)
        if fallback_engine and fallback_engine != primary_engine:
            logger.info("Fallback engine configured: %s", fallback_engine)

        subtitle_mode = "word" if enable_split else "sentence"
        logger.info("Subtitle mode: %s (enable_split=%s)", subtitle_mode, enable_split)

        # 执行转录（包含自动fallback机制）
        srt_content = transcribe_with_engine(
            engine_type=primary_engine,
            audio_file_path=preprocessed_audio_path,
            progress_cb=transcribe_cb,
            fallback_engine=fallback_engine,
            language=src_lang,
            subtitle_mode=subtitle_mode,
        )
        timestamp = int(time.time() * 1000)
        os.makedirs("work_dir/temp", exist_ok=True)
        # Debug: Check SRT content encoding before writing
        logger.debug(
            "[tasks.py] DEBUG: SRT content first 200 chars before writing: %s", repr(srt_content[:200])
        )
        with open(f"work_dir/temp/{timestamp}.srt", "w", encoding="utf-8") as f:
            f.write(srt_content)
        logger.info(
            "[tasks.py] SRT file saved to work_dir/temp/%s.srt with UTF-8 encoding", timestamp
        )
        _update(video_id, "transcribe", "Completed")
        logger.info(
            "Transcription completed for video %s, SRT content length: %s", video_id, len(srt_content)
        )
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        logger.error("Transcription failed for video %s: %s", video_id, exc)
        logger.error("TRACEBACK:\n%s", tb)
        _update(video_id, "transcribe", "Failed", detail=str(exc)[:200])
        return

    # 2. 优化字幕阶段（包含翻译）
    enable_translation = trans_lang and trans_lang != "None"

    # 定义文件路径
    original_srt_name = f"{video_id}_{src_lang}.srt"
    original_srt_path = os.path.join(SAVE_DIR, original_srt_name)

    translated_srt_name = None
    translated_srt_path = None
    if enable_translation:
        translated_srt_name = f"{video_id}_{trans_lang}.srt"
        translated_srt_path = os.path.join(SAVE_DIR, translated_srt_name)

    os.makedirs(SAVE_DIR, exist_ok=True)
    work_srt_path = f"work_dir/temp/{timestamp}.srt"

    # def optimise_state_cb(state: str):
    #     _update(video_id, "optimize", state)

    try:
        def optimize_progress_cb(value):
            """处理优化阶段进度：整数0-100 或 字符串状态"""
            if isinstance(value, (int, float)):
                _update(video_id, "optimize", "Running", progress=int(value))
            elif value == "Completed":
                _update(video_id, "optimize", "Completed", progress=100)
            elif value == "Running":
                _update(video_id, "optimize", "Running", progress=1)
            else:
                _update(video_id, "optimize", value)

        if enable_split:
            _update(video_id, "optimize", "Running")
            optimise_srt(
                srt_path=work_srt_path,
                save_path=original_srt_path,
                num_threads=_get_thread_count("split"),
                progress_cb=optimize_progress_cb,
            )
            _update(video_id, "optimize", "Completed")
        else:
            import shutil
            shutil.copy2(work_srt_path, original_srt_path)
            _update(video_id, "optimize", "Skipped")
            logger.info("[tasks.py] LLM split disabled, using ASR sentence-level output directly")

        # 第二步：翻译字幕（如果需要）
        if enable_translation and translated_srt_path:
            from utils.split_subtitle.main import translate_srt

            # 🆕 定义翻译进度回调（支持整数百分比）
            def translate_progress_cb(value):
                """处理翻译阶段进度：整数0-100 或 字符串状态"""
                if isinstance(value, (int, float)):
                    _update(video_id, "translate", "Running", progress=int(value))
                elif value == "Completed":
                    _update(video_id, "translate", "Completed", progress=100)
                elif value == "Running":
                    _update(video_id, "translate", "Running", progress=1)
                else:
                    _update(video_id, "translate", value)

            _update(video_id, "translate", "Running")
            translate_srt(
                raw_srt_path=original_srt_path,  # 使用优化后的原文字幕
                translate_srt_path=translated_srt_path,
                raw_lang=src_lang,
                target_lang=trans_lang,
                use_translation_cache=True,
                num_threads=_get_thread_count("translate"),  # 使用多线程翻译
                progress_cb=translate_progress_cb,  # 🆕 使用支持进度的回调
            )
            _update(video_id, "translate", "Completed")
        else:
            _update(video_id, "translate", "Completed")

    except Exception as exc:
        logger.error("字幕处理失败: %s", exc)
        _update(video_id, "optimize", "Failed")
        _update(video_id, "translate", "Failed")
        return

    # 更新数据库 - 保存原文字幕和翻译字幕路径
    with transaction.atomic():
        video.srt_path = original_srt_name
        if enable_translation and translated_srt_name:
            video.translated_srt_path = translated_srt_name
        video.save(update_fields=["srt_path", "translated_srt_path"])


"""
所以你可以将external_transcription视为前端文件SettingsDialog.vue中可选择的另一个远程字幕生成引擎，可以在SettingsDialog.vue的”字幕引擎“中选择，
在DropdownList中展示的名称为：远程VidGo字幕服务，并在下方注释：
用户可在高性能主机中部署VidGo实例，并通过IP/域名链接，调用后端的字幕识别服务。
需要填写的内容为IP/域名与端口号，一个Switch Icon设置是否启用SSL.
如果启用了SSL，并使用域名，则无需填写端口号。
"""


def process_next_task() -> None:
    """被后台线程循环调用，逐个执行"""
    try:
        task_identifier = subtitle_task_queue.get_nowait()
    except Empty:
        return

    try:
        # 判断是内部任务还是外部任务
        if task_identifier.startswith("ext_"):
            # 外部转录任务
            generate_external_transcription(task_identifier)
        else:
            # 内部视频转录任务
            video_id = int(task_identifier)
            generate_subtitles_for_video(video_id)
    finally:
        subtitle_task_queue.task_done()


class SubtitleTaskStatusView(View):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        logger.debug("%s", subtitle_task_status)
        return JsonResponse(subtitle_task_status, safe=False)


"""
流媒体下载流程：

视频/音频分开下载到 work_dir/{video_id}/
执行 ffmpeg 合成视频
计算合成视频的 MD5 值作为文件名
最终文件存放：
视频 → MEDIA_ROOT/saved_video/{md5}.mp4
原始音频 → MEDIA_ROOT/saved_audio/{md5}.mp3
"""

download_status = defaultdict(
    lambda: {
        "stages": {  # 状态：Queued/Running/Completed/Failed
            "video": "Queued",
            "audio": "Queued",
            "merge": "Queued",
        },
        "stage_progress": {  # 🆕 各阶段进度百分比 (0-100)
            "video": 0,
            "audio": 0,
            "merge": 0,
        },
        "stage_weights": {  # 🆕 各阶段权重（用于计算总进度）
            "video": 0.40,  # 视频下载占40%
            "audio": 0.30,  # 音频下载占30%
            "merge": 0.30,  # FFmpeg合成占30%
        },
        "total_progress": 0,  # 🆕 总进度百分比 (0-100)
        "finished": False,
        "title": "",
        "url": "",
        "cid": "",
        "bvid": "",
    }
)


def dl_set(task_id: str, stage: str, status: str, progress: int = None):
    """
    更新阶段状态和进度

    Args:
        task_id: 任务ID
        stage: 阶段名称 (video/audio/merge)
        status: 状态 (Queued/Running/Completed/Failed)
        progress: 该阶段进度百分比 (0-100)，可选
    """
    with download_status_lock:
        task = download_status.get(task_id)
        if task is None:
            return
        if stage not in task["stages"]:
            return

        # 更新状态
        task["stages"][stage] = status

        # 更新阶段进度
        if progress is not None:
            clamped = min(100, max(0, progress))
            if status == "Running":
                task["stage_progress"][stage] = max(task["stage_progress"][stage], clamped)
            else:
                task["stage_progress"][stage] = clamped
        elif status == "Completed":
            task["stage_progress"][stage] = 100
        elif status == "Running" and task["stage_progress"][stage] == 0:
            task["stage_progress"][stage] = 1  # Running时至少显示1%

        # 🆕 计算总进度
        total = sum(
            task["stage_weights"][s] * task["stage_progress"][s]
            for s in task["stage_progress"]
        )
        task["total_progress"] = round(total, 1)

        # 检查是否全部完成
        task["finished"] = all(s == "Completed" for s in task["stages"].values())


from utils.stream_downloader.bili_download import (
    get_direct_media_link,
    download_file_with_progress,
    merge_audio_video,
    get_video_info,
)
from utils.stream_downloader.youtube_download import YouTubeDownloader
from .utils import format_duration
from utils.video_converter import VideoConverter
import requests
from yt_dlp import YoutubeDL


def download_thumbnail(thumbnail_url: str, md5_value: str) -> str:
    """下载缩略图并保存到本地，返回保存的文件路径"""
    if not thumbnail_url:
        return ""

    try:
        thumbnail_dir = os.path.join(settings.MEDIA_ROOT, "thumbnail")
        os.makedirs(thumbnail_dir, exist_ok=True)

        # 获取文件扩展名，默认为jpg
        ext = (
            thumbnail_url.split(".")[-1].lower()
            if "." in thumbnail_url.split("/")[-1]
            else "jpg"
        )
        if ext not in ["jpg", "jpeg", "png", "webp"]:
            ext = "jpg"

        thumbnail_filename = f"{md5_value}.{ext}"
        thumbnail_path = os.path.join(thumbnail_dir, thumbnail_filename)

        # 检查文件是否已存在
        if os.path.exists(thumbnail_path):
            return thumbnail_filename

        # 根据URL判断是B站还是YouTube，设置不同的headers
        if "ytimg.com" in thumbnail_url or "youtube.com" in thumbnail_url:
            # YouTube 缩略图
            headers = {
                "Referer": "https://www.youtube.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            }
        else:
            # Bilibili 缩略图
            headers = {
                "Referer": "https://www.bilibili.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            }

        resp = requests.get(thumbnail_url, headers=headers, timeout=30, stream=True)
        resp.raise_for_status()

        with open(thumbnail_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info("Thumbnail downloaded: %s", thumbnail_filename)
        return thumbnail_filename

    except Exception as e:
        logger.error("Failed to download thumbnail: %s", e)
        return ""


def download_youtube_video(task_id: str):
    """下载 YouTube 视频的完整流程"""
    with download_status_lock:
        task = download_status[task_id]
        video_id, url, title = task["video_id"], task["url"], task["title"]

    downloader = YouTubeDownloader()

    # 获取视频信息包括缩略图
    try:
        video_info = downloader.get_video_info(url)
        if not video_info:
            dl_set(task_id, "video", "Failed")
            return

        thumbnail_url = video_info.get("thumbnail", "")
        duration_seconds = video_info.get("duration", 0)
        logger.info(
            "YouTube video info - Thumbnail: %s, Duration: %ss", thumbnail_url, duration_seconds
        )
    except Exception as e:
        logger.error("Failed to get YouTube video info: %s", e)
        dl_set(task_id, "video", "Failed")
        return

    # 创建临时工作目录
    work_dir = f"work_dir/{video_id}"
    os.makedirs(work_dir, exist_ok=True)

    try:
        # 下载视频到临时目录
        dl_set(task_id, "video", "Running")
        output_path = downloader.download_video(
            url,
            work_dir,
            progress_callback=lambda percent: dl_set(
                task_id, "video", "Running", progress=int(percent)
            ),
        )
        if not output_path or not os.path.exists(output_path):
            dl_set(task_id, "video", "Failed")
            return
        dl_set(task_id, "video", "Completed")

        # YouTube 的 yt-dlp 通常会自动合并视频和音频
        # 所以我们跳过单独的音频下载和合并步骤
        dl_set(task_id, "audio", "Completed")
        dl_set(task_id, "merge", "Completed")

        # 创建保存视频的目录
        save_dir = os.path.join(settings.MEDIA_ROOT, "saved_video")
        os.makedirs(save_dir, exist_ok=True)

        # 计算文件的 MD5 值
        md5_hash = hashlib.md5()
        with open(output_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                md5_hash.update(chunk)
        md5_value = md5_hash.hexdigest()
        file_path = os.path.join(save_dir, f"{md5_value}.mp4")

        # 检查是否已经存在相同的文件
        existing_files = os.listdir(save_dir)
        file_exists = any(md5_value in fname for fname in existing_files)
        if file_exists:
            logger.info("Download the same YouTube video, so skip.")
            return

        import shutil

        # 移动文件到最终位置
        shutil.move(output_path, file_path)

        # 下载并保存缩略图 (支持YouTube缩略图)
        thumbnail_filename = download_thumbnail(thumbnail_url, md5_value)

        # 格式化视频时长
        formatted_duration = (
            format_duration(duration_seconds) if duration_seconds > 0 else None
        )

        # 保存到Video数据库中
        video = Video.objects.create(
            name=title,
            url=f"{md5_value}.mp4",
            thumbnail_url=thumbnail_filename,
            video_length=formatted_duration,
            video_source="youtube",
            source_url=url,
            category=None,  # 临时分类，后续可以修改
        )

        # 更新文件信息（文件大小、创建时间、时长秒数）
        from .utils import update_video_file_info

        update_video_file_info(video, save=True)

        logger.info(
            "YouTube video created with thumbnail: %s, duration: %s", thumbnail_filename, formatted_duration
        )

    except Exception as e:
        logger.error("YouTube download error: %s", e)
        dl_set(task_id, "video", "Failed")
        dl_set(task_id, "audio", "Failed")
        dl_set(task_id, "merge", "Failed")
    finally:
        # 清理临时工作目录
        try:
            import shutil

            if os.path.exists(work_dir):
                shutil.rmtree(work_dir)
        except Exception as e:
            logger.error("Error cleaning up work directory: %s", e)


def download_bilibili_video(task_id: str):
    with download_status_lock:
        task = download_status[task_id]
        bvid, cid, url, title = task["bvid"], task["cid"], task["url"], task["title"]
        # ✅ 优先使用任务状态中存储的duration（前端传递的单P时长）
        duration_seconds = task.get("duration")

    # Read Bilibili sessdata from config using load_all_settings function
    try:
        settings_data = load_all_settings()
        sessdata = settings_data.get("Media Credentials", {}).get(
            "bilibili_sessdata", ""
        )
        logger.debug("sessdata: %s", sessdata)
    except Exception as e:
        logger.error("Error loading settings: %s", e)
        sessdata = ""  # fallback to empty string if there's an error

    # 获取视频基本信息（缩略图）
    # ❌ 注意：get_video_info() 返回的 duration 是所有分P的总时长，不能使用！
    """
    错误示例 - get_video_info()返回的是总时长：
    {
        "pic_url": "http://i1.hdslb.com/bfs/archive/7384dbaa8e3012a818d022cd55213d4a9b83da53.jpg",
        "owner": "常春藤中英字幕课",
        "duration": 37804,  # ❌ 这是所有16个分P的总时长（10个小时）
        "title": "从零开始构建 Linux 系统 | Build a LinuxFromScratch System",
        "bvid": "BV1bhaizSEr2"
    }

    正确方案 - 使用 get_cid() 中每个分P的 duration：
    [
        {"cid": 123, "duration": 1975, "part": "Part 1"},  # ✅ 单P时长
        {"cid": 456, "duration": 2292, "part": "Part 2"},  # ✅ 单P时长
        ...
    ]
    """
    try:
        # 如果任务状态中没有duration，则通过cid匹配获取真实的单P时长（降级方案）
        if duration_seconds is None:
            from utils.stream_downloader.bili_download import get_cid

            logger.info(
                "[Fallback] Duration not provided, fetching via cid matching for cid=%s", cid
            )
            cids, data = get_cid(bvid=bvid)
            # 通过cid匹配找到对应的分P数据
            for item in data:
                if item["cid"] == cid:
                    duration_seconds = item.get("duration", 0)
                    logger.info("[Fallback] Matched cid=%s, duration=%ss", cid, duration_seconds)
                    break
            else:
                logger.warning("[Warning] cid=%s not found in pagelist, using 0", cid)
                duration_seconds = 0

        # 获取缩略图URL（仍需调用video_info，但不使用其duration字段）
        video_info = get_video_info(bvid=bvid)
        thumbnail_url = video_info.get("pic_url", "")
        logger.info("Thumbnail URL: %s", thumbnail_url)
        logger.info("Video duration (single part): %ss", duration_seconds)
    except Exception as e:
        logger.error("Failed to get video info: %s", e)
        thumbnail_url = ""
        if duration_seconds is None:
            duration_seconds = 0

    video_file, audio_file, output_file, urls = get_direct_media_link(
        bvid, cid=cid, title=title, sessdata=sessdata
    )

    # 🆕 定义各阶段的进度回调
    def video_progress_cb(percent):
        dl_set(task_id, "video", "Running", progress=percent)

    def audio_progress_cb(percent):
        dl_set(task_id, "audio", "Running", progress=percent)

    def merge_progress_cb(percent):
        dl_set(task_id, "merge", "Running", progress=percent)

    # 1.下载视频流
    dl_set(task_id, "video", "Running")
    download_file_with_progress(
        urls["vidBaseUrl"], video_file, progress_callback=video_progress_cb
    )
    dl_set(task_id, "video", "Completed")

    # 2.下载音频流
    dl_set(task_id, "audio", "Running")
    download_file_with_progress(
        urls["audBaseUrl"], audio_file, progress_callback=audio_progress_cb
    )
    dl_set(task_id, "audio", "Completed")

    # ③ 合并音视频
    dl_set(task_id, "merge", "Running")
    merge_audio_video(
        audio_file, video_file, output_file, progress_callback=merge_progress_cb
    )
    for fpath in [video_file]:
        try:
            os.remove(fpath)
        except OSError:
            pass
    dl_set(task_id, "merge", "Completed")

    # ④ AV1转换阶段 (部分视频下载下来是H.265，需要转化成av1以便旧浏览器兼容，该代码默认关闭)
    # from utils.video_converter import VideoConverter
    # converter = VideoConverter()

    # # 检查是否需要转换为AV1
    # if converter.should_convert_to_av1(str(output_file)):
    #     print(f"Converting {output_file} to AV1 format...")
    #     dl_set(task_id, "convert", "Running")

    #     # 生成AV1输出文件路径
    #     av1_output_file = str(output_file).replace('.mp4', '_av1.mp4')

    #     def conversion_progress_callback(status):
    #         dl_set(task_id, "convert", status)

    #     # 执行AV1转换
    #     conversion_success = converter.convert_to_av1(
    #         str(output_file),
    #         av1_output_file,
    #         progress_callback=conversion_progress_callback
    #     )

    #     if conversion_success and os.path.exists(av1_output_file):
    #         # 转换成功，删除原文件，使用AV1文件
    #         try:
    #             os.remove(output_file)
    #             os.rename(av1_output_file, str(output_file))
    #             print(f"AV1 conversion successful: {output_file}")
    #             dl_set(task_id, "convert", "Completed")
    #         except OSError as e:
    #             print(f"Error replacing original file with AV1: {e}")
    #             dl_set(task_id, "convert", "Failed")
    #             # 如果替换失败，继续使用原文件
    #     else:
    #         print(f"AV1 conversion failed, keeping original file: {output_file}")
    #         dl_set(task_id, "convert", "Failed")
    #         # 转换失败但不影响整个下载流程，继续使用原文件
    # else:
    #     print(f"Video codec is already browser-compatible, skipping AV1 conversion")

    # 创建保存视频的目录
    save_dir = os.path.join(settings.MEDIA_ROOT, "saved_video")
    os.makedirs(save_dir, exist_ok=True)
    # 计算文件的 MD5 值
    md5_hash = hashlib.md5()
    with open(output_file, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):  # 每次 8 KB
            md5_hash.update(chunk)
    md5_value = md5_hash.hexdigest()
    file_path = os.path.join(save_dir, f"{md5_value}.mp4")
    logger.info("To be downloaded: %s", file_path)

    # 检查是否已经存在相同的文件
    existing_files = os.listdir(save_dir)
    file_exists = any(md5_value in fname for fname in existing_files)
    if file_exists:
        logger.error("Download the same file from bilibili,so raise error.")
        return
    import shutil

    # 移动单个文件
    logger.info("To be moved: %s", file_path)
    shutil.move(output_file, file_path)

    # 下载并保存缩略图
    thumbnail_filename = download_thumbnail(thumbnail_url, md5_value)

    # 格式化视频时长
    formatted_duration = (
        format_duration(duration_seconds) if duration_seconds > 0 else None
    )
    logger.info("formatted_duration: %s seconds", formatted_duration)
    # 处理流程完成后不需要再次设置merge状态
    # 保存到Video数据库中
    video = Video.objects.create(
        name=title,
        url=f"{md5_value}.mp4",
        thumbnail_url=thumbnail_filename,  # 保存缩略图文件名
        video_length=formatted_duration,  # 保存视频时长
        video_source="bilibili",
        source_url=url,
        category=None,  # temperaryly no,Can be set later
    )

    # 更新文件信息（文件大小、创建时间、时长秒数）
    from .utils import update_video_file_info

    update_video_file_info(video, save=True)

    logger.info(
        "Video created with thumbnail: %s, duration: %s", thumbnail_filename, formatted_duration
    )


def download_podcast_audio(task_id: str):
    """下载 Apple Podcast 音频的完整流程"""
    with download_status_lock:
        task = download_status[task_id]
        episode_id, title = task["episode_id"], task["title"]
        url = task["url"]

    # 创建临时工作目录
    work_dir = f"work_dir/{episode_id}"
    os.makedirs(work_dir, exist_ok=True)

    try:
        # 使用 yt-dlp 下载 Apple Podcast 音频
        dl_set(task_id, "video", "Running")  # 复用video阶段表示音频下载

        # 配置 yt-dlp 选项，优先下载 m4a，然后 mp3
        ydl_opts = {
            "format": "best[ext=m4a]/best[ext=mp3]/best",
            "outtmpl": f"{work_dir}/{title}.%(ext)s",
            "writeinfojson": False,  # 不保存元数据
        }
        ydl_opts["progress_hooks"] = [
            lambda d: dl_set(
                task_id,
                "video",
                "Running",
                progress=int(
                    min(
                        (
                            ((d.get("downloaded_bytes") or 0) / (d.get("total_bytes") or d.get("total_bytes_estimate") or 1))
                            * 100
                        ),
                        99.0,
                    )
                ),
            )
            if d.get("status") == "downloading"
            else (
                dl_set(task_id, "video", "Running", progress=100)
                if d.get("status") == "finished"
                else None
            )
        ]

        # 配置代理
        try:
            settings_data = load_all_settings()
            use_download_proxy = (
                settings_data.get("Media Credentials", {})
                .get("download_use_proxy", "false")
                .lower()
                == "true"
            )
            from video.proxy import get_effective_proxy

            proxy = get_effective_proxy(use_download_proxy)
            if proxy:
                ydl_opts["proxy"] = proxy
        except Exception as e:
            logger.error("Error checking proxy settings for podcast: %s", e)

        # 加载 cookies（仅 YouTube 链接需要）
        if "youtube.com" in url or "youtu.be" in url:
            _cookies_path = os.path.join(
                settings.MEDIA_ROOT, "cookies", "youtube-cookies.txt"
            )
            if os.path.exists(_cookies_path):
                ydl_opts["cookiefile"] = _cookies_path

        # 获取音频信息包括缩略图
        info = None
        info_ydl_opts = {"quiet": True, "no_download": True}
        if "proxy" in ydl_opts:
            info_ydl_opts["proxy"] = ydl_opts["proxy"]
        if "cookiefile" in ydl_opts:
            info_ydl_opts["cookiefile"] = ydl_opts["cookiefile"]
        with YoutubeDL(info_ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            dl_set(task_id, "video", "Failed")
            return

        thumbnail_url = info.get("thumbnail", "")
        duration_seconds = info.get("duration", 0)

        # 下载音频文件
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # 查找下载的音频文件
        downloaded_files = [
            f for f in os.listdir(work_dir) if f.endswith((".m4a", ".mp3"))
        ]
        if not downloaded_files:
            dl_set(task_id, "video", "Failed")
            return

        audio_file = os.path.join(work_dir, downloaded_files[0])

        if not os.path.exists(audio_file):
            dl_set(task_id, "video", "Failed")
            return

        dl_set(task_id, "video", "Completed")

        # 跳过音频和合并阶段（因为已经是音频文件）
        dl_set(task_id, "audio", "Completed")
        dl_set(task_id, "merge", "Completed")

        # 创建保存音频的目录 - 注意这里保存到 saved_audio 而不是 saved_video
        save_dir = os.path.join(settings.MEDIA_ROOT, "saved_audio")
        os.makedirs(save_dir, exist_ok=True)

        # 计算文件的 MD5 值
        md5_hash = hashlib.md5()
        with open(audio_file, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                md5_hash.update(chunk)
        md5_value = md5_hash.hexdigest()

        # 保持原始扩展名（m4a 或 mp3）
        file_ext = os.path.splitext(audio_file)[1]  # 获取扩展名 .m4a 或 .mp3
        file_path = os.path.join(save_dir, f"{md5_value}{file_ext}")

        # 检查是否已经存在相同的文件
        if os.path.exists(file_path):
            logger.info("Download the same podcast audio, so skip.")
            return

        # 移动文件到最终位置
        import shutil

        shutil.move(audio_file, file_path)

        # 下载并保存缩略图
        thumbnail_filename = download_thumbnail(thumbnail_url, md5_value)

        # 格式化音频时长
        formatted_duration = (
            format_duration(duration_seconds) if duration_seconds > 0 else None
        )

        # 保存到Video数据库中（复用Video模型存储音频信息）
        video = Video.objects.create(
            name=title,
            url=f"{md5_value}{file_ext}",  # 保存带扩展名的文件名
            thumbnail_url=thumbnail_filename,
            video_length=formatted_duration,
            video_source="podcast",
            source_url=url,
            category=None,  # 使用不同的分类ID区分播客音频
        )

        # 更新文件信息（文件大小、创建时间、时长秒数）
        from .utils import update_video_file_info

        update_video_file_info(video, save=True)

        logger.info(
            "Podcast audio created with thumbnail: %s, duration: %s, ext: %s", thumbnail_filename, formatted_duration, file_ext
        )

    except Exception as e:
        logger.error("Apple Podcast download error: %s", e)
        dl_set(task_id, "video", "Failed")
        dl_set(task_id, "audio", "Failed")
        dl_set(task_id, "merge", "Failed")
    finally:
        # 清理临时工作目录
        try:
            import shutil

            if os.path.exists(work_dir):
                shutil.rmtree(work_dir)
        except Exception as e:
            logger.error("Error cleaning up work directory: %s", e)


def download_stream_media(task_id: str):
    """平台分发器：根据平台类型调用相应的下载函数"""
    with download_status_lock:
        task = download_status[task_id]
        platform = task.get("platform", "bilibili")  # 默认为bilibili以保持向后兼容

    logger.info("Starting download for task %s, platform: %s", task_id, platform)

    if platform == "youtube":
        download_youtube_video(task_id)
    elif platform == "apple_podcast":
        download_podcast_audio(task_id)
    else:  # bilibili 或其他未知平台默认使用bilibili处理器
        download_bilibili_video(task_id)


# 这里可以构思一下多线程下载的方式，暂时先单线程
def process_download_task() -> None:
    """被后台线程循环调用"""
    try:
        task_id = download_queue.get_nowait()
    except Empty:
        return
    try:
        download_stream_media(task_id)  # 每个任务对应一个视频
    finally:
        download_queue.task_done()



# ── vidUnder Summary Task ──────────────────────────────────────

summary_task_queue: Queue[str] = Queue()

summary_task_status = defaultdict(
    lambda: {
        "video_id": 0,
        "video_name": "",
        "video_path": "",
        "srt_path": "",
        "stages": {
            "build": "Queued",
            "extract": "Queued",
            "summarize": "Queued",
        },
        "stage_progress": {
            "build": 0,
            "extract": 0,
            "summarize": 0,
        },
        "stage_detail": {
            "build": "",
            "extract": "",
            "summarize": "",
        },
        "stage_weights": {
            "build": 0.40,
            "extract": 0.30,
            "summarize": 0.30,
        },
        "total_progress": 0,
        "status": "Queued",
        "result_path": "",
        "error_message": "",
        "created_at": 0,
    }
)


def _summary_update(task_id: str, stage: str, status: str, progress: int = None, detail: str = None):
    task = summary_task_status.get(task_id)
    if task is None:
        return
    if stage not in task["stages"]:
        return
    task["stages"][stage] = status
    if detail is not None:
        task["stage_detail"][stage] = detail
    if progress is not None:
        clamped = min(100, max(0, progress))
        if status == "Running":
            task["stage_progress"][stage] = max(task["stage_progress"][stage], clamped)
        else:
            task["stage_progress"][stage] = clamped
    elif status == "Completed":
        task["stage_progress"][stage] = 100
    elif status == "Running" and task["stage_progress"][stage] == 0:
        task["stage_progress"][stage] = 2.5
    total = sum(
        task["stage_weights"][s] * task["stage_progress"][s]
        for s in task["stage_progress"]
    )
    task["total_progress"] = round(total, 1)
    # Update overall status
    if all(s == "Completed" for s in task["stages"].values()):
        task["status"] = "Completed"
    elif any(s == "Failed" for s in task["stages"].values()):
        task["status"] = "Failed"
    elif any(s == "Running" for s in task["stages"].values()):
        task["status"] = "Running"


def _inject_vidunder_config():
    """Read Video Understanding settings from config.ini and patch vid_under config module."""
    settings_file = os.path.join(settings.BASE_DIR, "./config/config.ini")
    if not os.path.exists(settings_file):
        return
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(settings_file)

    def g(key, fallback=""):
        return cfg.get("Video Understanding", key, fallback=fallback)

    import config as vu_config
    import external_api as vu_ext

    # Corner Detection
    provider = g("vu_corner_provider", "gemini")
    if provider == "gemini":
        vu_config.OPENROUTER_KEY = g("vu_corner_gemini_api_key") or vu_config.OPENROUTER_KEY
        vu_config.OPENROUTER_BASE_URL = g("vu_corner_gemini_base_url") or vu_config.OPENROUTER_BASE_URL
        if g("vu_corner_gemini_model"):
            vu_config.OPENROUTER_MODEL = g("vu_corner_gemini_model")
    elif provider == "mimo":
        if g("vu_corner_mimo_api_key"):
            vu_config.MIMO_API_KEY = g("vu_corner_mimo_api_key")
        if g("vu_corner_mimo_base_url"):
            vu_config.MIMO_BASE_URL = g("vu_corner_mimo_base_url")
        if g("vu_corner_mimo_model"):
            vu_config.MIMO_MODEL = g("vu_corner_mimo_model")
    elif provider == "openai_compatible":
        key = g("vu_corner_openai_api_key")
        base = g("vu_corner_openai_base_url")
        model = g("vu_corner_openai_model")
        if key:
            vu_config.OPENROUTER_KEY = key
        if base:
            vu_config.OPENROUTER_BASE_URL = base
        if model:
            vu_config.OPENROUTER_MODEL = model

    # Summary Orchestration (DeepSeek)
    if g("vu_summary_api_key"):
        vu_config.DEEPSEEK_API_KEY = g("vu_summary_api_key")
    if g("vu_summary_base_url"):
        vu_config.DEEPSEEK_BASE_URL = g("vu_summary_base_url")
    if g("vu_summary_model"):
        vu_config.DEEPSEEK_MODEL = g("vu_summary_model")

    # Knowledge LLM
    kn_provider = g("vu_knowledge_provider", "doubao")
    if kn_provider == "doubao":
        if g("vu_knowledge_api_key"):
            vu_config.DOUBAO_API_KEY = g("vu_knowledge_api_key")
        if g("vu_knowledge_base_url"):
            vu_config.DOUBAO_BASE_URL = g("vu_knowledge_base_url")
        if g("vu_knowledge_model"):
            vu_config.DOUBAO_MODEL = g("vu_knowledge_model")
    elif kn_provider == "step":
        if g("vu_knowledge_api_key"):
            vu_config.STEP_API_KEY = g("vu_knowledge_api_key")
        if g("vu_knowledge_base_url"):
            vu_config.STEP_BASE_URL = g("vu_knowledge_base_url")
        if g("vu_knowledge_model"):
            vu_config.STEP_MODEL = g("vu_knowledge_model")
    elif kn_provider == "openrouter":
        if g("vu_knowledge_api_key"):
            vu_config.OPENROUTER_KEY = g("vu_knowledge_api_key")
        if g("vu_knowledge_base_url"):
            vu_config.OPENROUTER_BASE_URL = g("vu_knowledge_base_url")
        if g("vu_knowledge_model"):
            vu_config.OPENROUTER_MODEL = g("vu_knowledge_model")
    elif kn_provider == "openai_compatible":
        key = g("vu_knowledge_api_key")
        base = g("vu_knowledge_base_url")
        model = g("vu_knowledge_model")
        if key:
            vu_config.DOUBAO_API_KEY = key
            vu_config.OPENROUTER_KEY = key
        if base:
            vu_config.DOUBAO_BASE_URL = base
            vu_config.OPENROUTER_BASE_URL = base
        if model:
            vu_config.DOUBAO_MODEL = model

    # Sync to external_api module-level imports
    vu_ext.OPENROUTER_KEY = vu_config.OPENROUTER_KEY
    vu_ext.OPENROUTER_BASE_URL = vu_config.OPENROUTER_BASE_URL
    vu_ext.OPENROUTER_MODEL = vu_config.OPENROUTER_MODEL
    vu_ext.DOUBAO_API_KEY = vu_config.DOUBAO_API_KEY
    vu_ext.DOUBAO_BASE_URL = vu_config.DOUBAO_BASE_URL
    vu_ext.DOUBAO_MODEL = vu_config.DOUBAO_MODEL
    vu_ext.DEEPSEEK_API_KEY = vu_config.DEEPSEEK_API_KEY
    vu_ext.DEEPSEEK_BASE_URL = vu_config.DEEPSEEK_BASE_URL
    vu_ext.STEP_API_KEY = vu_config.STEP_API_KEY
    vu_ext.STEP_BASE_URL = vu_config.STEP_BASE_URL
    vu_ext.STEP_MODEL = vu_config.STEP_MODEL
    vu_ext.MIMO_API_KEY = vu_config.MIMO_API_KEY
    vu_ext.MIMO_BASE_URL = vu_config.MIMO_BASE_URL
    vu_ext.MIMO_MODEL = vu_config.MIMO_MODEL


def generate_summary_for_video(task_id: str) -> None:
    """Run the 3-step vidUnder pipeline: build → extract → summarize."""
    task = summary_task_status[task_id]
    try:
        task["status"] = "Running"
        import sys, os
        vid_under_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vid_under")
        if vid_under_dir not in sys.path:
            sys.path.insert(0, vid_under_dir)

        video_path = task["video_path"]
        srt_path = task["srt_path"]

        os.environ["VIDUNDER_VIDEO_PATH"] = video_path
        os.environ["VIDUNDER_SRT_PATH"] = srt_path

        _inject_vidunder_config()

        db_dir = os.path.join(vid_under_dir, "..", "media", "vidunder", "db")
        os.makedirs(db_dir, exist_ok=True)

        # Step 1: build
        _summary_update(task_id, "build", "Running", detail="Starting MiniCPM-V caption...")
        from video_db import build_database
        import time as _time
        db_name = _time.strftime("%Y%m%d_%H%M%S") + "_" + str(task.get("video_id", 0))
        build_database(video_path, srt_path, db_name=db_name)
        _summary_update(task_id, "build", "Completed")

        # Step 2: extract
        _summary_update(task_id, "extract", "Running", detail="Running GLM-OCR extraction...")
        import tempfile
        extract_output = os.path.join(tempfile.gettempdir(), db_name)
        os.makedirs(extract_output, exist_ok=True)
        from content_extractor import extract_unique_slides, ocr_slides
        from layout_detector import detect_layout, crop_content, get_vision_bbox
        from main import cmd_extract
        cmd_extract(video_path, srt_path=srt_path, output_dir=extract_output)
        _summary_update(task_id, "extract", "Completed")

        # Step 3: summarize
        _summary_update(task_id, "summarize", "Running", detail="Generating summary via DeepSeek...")
        from agent import VideoAgent
        from srt_utils import parse_srt
        import json as _json

        db_path = os.path.join(db_dir, f"{db_name}.json")
        with open(db_path, encoding="utf-8") as f:
            db = _json.load(f)
        srt = parse_srt(srt_path)
        agent = VideoAgent(db, srt, lang=task.get("language", "中文"))
        summary = agent.summarize(min_coverage=task.get("min_coverage", 0.60))

        # Save result
        result_dir = os.path.join(vid_under_dir, "..", "media", "vidunder", "output")
        os.makedirs(result_dir, exist_ok=True)
        result_path = os.path.join(result_dir, f"{db_name}_summary.md")
        with open(result_path, "w", encoding="utf-8") as f:
            f.write(summary)

        import shutil
        src_slides = os.path.join(extract_output, "slides")
        dst_slides = os.path.join(result_dir, f"{db_name}_slides")
        if os.path.isdir(src_slides) and not os.path.isdir(dst_slides):
            shutil.copytree(src_slides, dst_slides)

        task["result_path"] = result_path
        _summary_update(task_id, "summarize", "Completed")
        task["status"] = "Completed"

    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        logger.error("Summary task %s failed: %s\n%s", task_id, exc, tb)
        task["error_message"] = str(exc)[:500]
        for stage in ["build", "extract", "summarize"]:
            if task["stages"][stage] == "Running":
                _summary_update(task_id, stage, "Failed", detail=str(exc)[:200])
                break
        task["status"] = "Failed"


def process_summary_task() -> None:
    """Background worker: process one summary task from queue."""
    try:
        task_id = summary_task_queue.get_nowait()
    except Empty:
        return
    try:
        generate_summary_for_video(task_id)
    finally:
        summary_task_queue.task_done()
