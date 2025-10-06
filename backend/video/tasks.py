from django.views import View
import os, time
from queue import Queue, Empty
from collections import defaultdict
from django.http import JsonResponse
from django.db import transaction
from .models import Video
from utils.split_subtitle.main import optimise_srt
from django.conf import settings  # 确保这个在顶部
import hashlib
from .views.set_setting import load_all_settings
from utils.wsr.transcription_engine import transcribe_with_engine
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

subtitle_task_queue: Queue[str] = Queue()  # 改为 str 类型，支持 video_id 和 external_task_id
download_queue: Queue[int] = Queue()
tts_queue: Queue[str] = Queue()  # TTS任务队列
SAVE_DIR = 'media/saved_srt'

# 线程锁保护 download_status 的并发访问
import threading
download_status_lock = threading.RLock()

# 外部转录任务状态跟踪
external_task_status = defaultdict(lambda: {
    "task_id": "",
    "filename": "",
    "audio_file_path": "",
    "task_type": "external",  # 标识为外部任务
    "created_at": 0,
    "status": "Queued",  # 队列中、运行中、已完成、失败
    "result_file": "",
    "error_message": "",
})

# 🆕 实时字幕流状态跟踪（sentence-by-sentence）
realtime_subtitle_status = defaultdict(lambda: {
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
})

# TTS任务状态跟踪
tts_task_status = defaultdict(lambda: {
    "task_id": "",
    "video_id": 0,
    "video_name": "",
    "language": "zh",  # zh/en/jp
    "voice": "longxiaochun_v2",
    "status": "Queued",  # Queued/Running/Completed/Failed
    "progress": 0,  # 进度百分比 0-100
    "total_segments": 0,
    "completed_segments": 0,
    "output_file": "",  # 生成的音频文件名
    "error_message": "",
    "created_at": 0,
})

# 每个 video_id 对应 3 个阶段
# stages = 0: 字级时间戳 1: 大模型优化 2: 翻译
subtitle_task_status = defaultdict(lambda: {
    "filename": "",
    "src_lang": "None",
    "trans_lang": "None",  # 要翻译成的语言 None(表示不翻译),zh,en,jp
    "video_id": 0,
    "stages": {
        "transcribe":  "Queued",
        "optimize":    "Queued",
        "translate":   "Queued",
    },
    # 🆕 进度追踪系统
    "stage_progress": {       # 各阶段进度百分比 (0-100)
        "transcribe": 0,
        "optimize": 0,
        "translate": 0,
    },
    "stage_detail": {         # 各阶段详细进度信息
        "transcribe": "",
        "optimize": "",
        "translate": "",
    },
    "stage_weights": {        # 各阶段权重（40:30:30）
        "transcribe": 0.40,   # 字幕生成占40%
        "optimize": 0.30,     # 字幕优化占30%
        "translate": 0.30,    # 翻译占30%
    },
    "total_progress": 0,      # 总进度百分比 (0-100)
    "optimize_total_chunks": 0,    # 优化任务总chunk数
    "optimize_completed_chunks": 0, # 优化已完成chunk数
    "translate_total_chunks": 0,    # 翻译任务总chunk数
    "translate_completed_chunks": 0, # 翻译已完成chunk数
})
FIXED_NUM_THREADS = 8

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
def _update(video_id: int, stage: str, status: str, progress: int = None, detail: str = None):
    """
    更新字幕任务的阶段状态和进度

    Args:
        video_id: 视频ID
        stage: 阶段名称 (transcribe/optimize/translate)
        status: 状态 (Queued/Running/Completed/Failed)
        progress: 该阶段进度百分比 (0-100)，可选
        detail: 详细进度信息（如"Segment 2/6 (33%)"），可选
    """
    task = subtitle_task_status[video_id]
    task["stages"][stage] = status

    # 更新详细进度信息
    if detail is not None:
        if "stage_detail" not in task:
            task["stage_detail"] = {}
        task["stage_detail"][stage] = detail

    # 更新阶段进度
    if progress is not None:
        task["stage_progress"][stage] = min(100, max(0, progress))
    elif status == "Completed":
        task["stage_progress"][stage] = 100
    elif status == "Running" and task["stage_progress"][stage] == 0:
        task["stage_progress"][stage] = 2.5  # Running时至少显示2.5% (权重0.4时总进度为1%)

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
    temp_audio_dir = 'work_dir/temp_audio'
    os.makedirs(temp_audio_dir, exist_ok=True)
    
    # 生成预处理后的音频文件路径
    preprocessed_audio_path = os.path.join(temp_audio_dir, f"{video_id}.mp3")
    
    # 检查是否已经存在预处理后的文件
    if os.path.exists(preprocessed_audio_path):
        print(f"Preprocessed audio already exists: {preprocessed_audio_path}")
        return preprocessed_audio_path
    
    print(f"Preprocessing audio: {original_audio_path} -> {preprocessed_audio_path}")
    
    # 使用FFmpeg转换为单声道MP3格式
    ffmpeg_cmd = [
        'ffmpeg',
        '-i', original_audio_path,
        '-ac', '1',          # 转换为单声道
        '-ar', '16000',      # 设置采样率为16kHz (Whisper推荐)
        '-ab', '128k',       # 音频比特率128k (平衡质量和大小)
        '-acodec', 'mp3',    # 使用MP3编码器
        '-y',                # 覆盖输出文件
        preprocessed_audio_path
    ]
    
    try:
        print(f"FFmpeg command: {' '.join(ffmpeg_cmd)}")
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )
        
        if result.returncode == 0 and os.path.exists(preprocessed_audio_path):
            audio_size = os.path.getsize(preprocessed_audio_path)
            print(f"Audio preprocessing successful: {preprocessed_audio_path} ({audio_size} bytes)")
            return preprocessed_audio_path
        else:
            print(f"FFmpeg preprocessing failed: {result.stderr}")
            raise Exception(f"Audio preprocessing failed: {result.stderr}")
    
    except subprocess.TimeoutExpired:
        raise Exception("Audio preprocessing timed out")
    except Exception as e:
        raise Exception(f"Audio preprocessing error: {str(e)}")

def handle_translation_only(video_id: int, video, src_lang: str, trans_lang: str, emphasize_dst: str = "") -> None:
    """处理仅翻译模式的字幕任务"""
    try:
        # 获取视频的原始语言，如果没有设置则使用src_lang
        original_lang = video.raw_lang or src_lang
        if original_lang == "existing":
            # 查找已有的字幕文件
            original_lang = video.raw_lang or 'en'  # 默认为英文
        
        # 查找原文字幕文件
        original_srt_name = f"{video_id}_{original_lang}.srt"
        original_srt_path = os.path.join(SAVE_DIR, original_srt_name)
        
        if not os.path.exists(original_srt_path):
            # 如果找不到指定语言的字幕，尝试查找任何已有的字幕文件
            for lang in ['en', 'zh', 'jp']:
                alt_srt_name = f"{video_id}_{lang}.srt"
                alt_srt_path = os.path.join(SAVE_DIR, alt_srt_name)
                if os.path.exists(alt_srt_path):
                    original_srt_path = alt_srt_path
                    original_lang = lang
                    break
            else:
                raise Exception(f'Original subtitle file not found for video {video_id}. Please generate original subtitles first.')
        
        print(f"Using original subtitle file: {original_srt_path}")
        
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
            num_threads=FIXED_NUM_THREADS,
            progress_cb=lambda status: _update(video_id, "translate", status),
            terms_to_note=emphasize_dst,
        )
        _update(video_id, "translate", "Completed")
        
        # 更新数据库 - 只更新翻译字幕路径
        with transaction.atomic():
            video.translated_srt_path = translated_srt_name
            video.save(update_fields=["translated_srt_path"])
        
        print(f"Translation completed for video {video_id}: {original_lang} -> {trans_lang}")
        
    except Exception as exc:
        print(f"Translation-only failed for video {video_id}: {exc}")
        _update(video_id, "translate", "Failed")
        raise exc

def generate_external_transcription(task_id: str) -> None:
    """处理外部转录任务，只输出字级时间戳字幕"""
    task = external_task_status[task_id]
    
    try:
        task["status"] = "Running"
        audio_file_path = task["audio_file_path"]
        
        print(f"Starting external transcription for task {task_id}: {task['filename']}")
        
        # 外部转录任务强制使用本地faster_whisper引擎，避免递归调用
        from utils.wsr.fast_wsr import transcribe_audio
        
        # 状态更新回调
        def progress_cb(status):
            print(f"External task {task_id} progress: {status}")
        
        # 直接使用本地faster_whisper引擎执行转录
        print(f"Using local faster_whisper engine for external task {task_id}")
        srt_content = transcribe_audio(audio_file_path, progress_cb)
        
        # 保存结果文件
        external_result_dir = 'work_dir/external_results'
        os.makedirs(external_result_dir, exist_ok=True)
        result_file = os.path.join(external_result_dir, f"{task_id}.srt")
        
        with open(result_file, 'w', encoding='utf-8') as f:
            f.write(srt_content)
        
        # 更新任务状态
        task["status"] = "Completed"
        task["result_file"] = result_file
        
        print(f"External transcription completed for task {task_id}")
        
    except Exception as exc:
        print(f"External transcription failed for task {task_id}: {exc}")
        task["status"] = "Failed"
        task["error_message"] = str(exc)

def generate_subtitles_for_video(video_id: int) -> None:
    """内部字幕生成，字幕生成中真正干活的函数,也是每个video_id的Task在做的事"""
    task  = subtitle_task_status[video_id]
    
    video = Video.objects.get(pk=video_id)
    filename,src_lang,trans_lang=task["filename"],task["src_lang"],task["trans_lang"]
    print(filename,src_lang,trans_lang)
    emphasize_dst = task.get("emphasize_dst", "")  # 获取术语信息
    translation_only = task.get("translation_only", False)  # 检查是否为仅翻译模式
    
    if not video:
        raise Exception('Video not found')
    video_path = video.url  

    # 检查是否为仅翻译模式
    if translation_only:
        print(f"Translation-only mode for video {video_id}")
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
            _update(video_id, "transcribe", "Running",
                   progress=int(status),
                   detail=f"{int(status)}% transcribing...")
        # 检查是否为段级进度信息
        elif isinstance(status, str):
            segment_match = re.match(r'Segment (\d+)/(\d+) \((\d+)%\)', status)
            if segment_match:
                completed, total, percent = segment_match.groups()
                _update(video_id, "transcribe", "Running",
                       progress=int(percent),
                       detail=status)
            else:
                # 普通状态字符串
                _update(video_id, "transcribe", status)
    print("start transcribing:", video_path)
    
    try:
        _update(video_id, "transcribe", "Running")
        
        # 预处理音频文件：转换为单声道MP3格式
        preprocessed_audio_path = preprocess_audio_for_transcription(video_id)
        print(f"Transcribing preprocessed audio file: {preprocessed_audio_path}")
        
        # 使用统一的转录引擎接口
        from utils.wsr.transcription_engine import transcribe_with_engine, load_transcription_settings
        
        # 加载转录引擎配置
        settings = load_transcription_settings()
        transcription_settings = settings.get('Transcription Engine', {})
        
        primary_engine = transcription_settings.get('primary_engine', 'whisper_cpp')
        fallback_engine = transcription_settings.get('fallback_engine', '')
        
        print(f"Using primary transcription engine: {primary_engine}")
        if fallback_engine and fallback_engine != primary_engine:
            print(f"Fallback engine configured: {fallback_engine}")
        
        # 执行转录（包含自动fallback机制）
        srt_content = transcribe_with_engine(
            engine_type=primary_engine,
            audio_file_path=preprocessed_audio_path,
            progress_cb=transcribe_cb,
            fallback_engine=fallback_engine,
            language=src_lang  # 传递用户指定的源语言
        )
        timestamp=int(time.time()*1000)
        os.makedirs('work_dir/temp', exist_ok=True)
        # Debug: Check SRT content encoding before writing
        print(f"[tasks.py] DEBUG: SRT content first 200 chars before writing: {repr(srt_content[:200])}")
        with open(f'work_dir/temp/{timestamp}.srt', 'w', encoding='utf-8') as f:
            f.write(srt_content)
        print(f"[tasks.py] SRT file saved to work_dir/temp/{timestamp}.srt with UTF-8 encoding")
        _update(video_id, "transcribe", "Completed")
        print(f"Transcription completed for video {video_id}, SRT content length: {len(srt_content)}")
    except Exception as exc:
        print(f"Transcription failed for video {video_id}: {exc}")
        _update(video_id, "transcribe", "Failed")
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
    work_srt_path = f'work_dir/temp/{timestamp}.srt'
    
    # def optimise_state_cb(state: str):
    #     _update(video_id, "optimize", state)
    
    try:
        # 🆕 定义优化进度回调（支持整数百分比）
        def optimize_progress_cb(value):
            """处理优化阶段进度：整数0-100 或 字符串状态"""
            if isinstance(value, (int, float)):
                # 整数进度 -> 直接传递
                _update(video_id, "optimize", "Running", progress=int(value))
            elif value == "Completed":
                _update(video_id, "optimize", "Completed", progress=100)
            elif value == "Running":
                _update(video_id, "optimize", "Running", progress=1)
            else:
                _update(video_id, "optimize", value)

        # 第一步：优化字幕
        _update(video_id, "optimize", "Running")
        optimise_srt(
            srt_path=work_srt_path,
            save_path=original_srt_path,  # 保存优化后的原文字幕
            num_threads=FIXED_NUM_THREADS,
            progress_cb=optimize_progress_cb,  # 🆕 使用支持进度的回调
        )
        _update(video_id, "optimize", "Completed")
        
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
                num_threads=FIXED_NUM_THREADS,  # 使用多线程翻译
                progress_cb=translate_progress_cb,  # 🆕 使用支持进度的回调
            )
            _update(video_id, "translate", "Completed")
        else:
            _update(video_id, "translate", "Completed")
            
    except Exception as exc:
        print(f"字幕处理失败: {exc}")
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
        if task_identifier.startswith('ext_'):
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
        print(subtitle_task_status)
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
        "stages": {              # 状态：Queued/Running/Completed/Failed
            "video": "Queued",
            "audio": "Queued",
            "merge": "Queued",
        },
        "stage_progress": {      # 🆕 各阶段进度百分比 (0-100)
            "video": 0,
            "audio": 0,
            "merge": 0,
        },
        "stage_weights": {       # 🆕 各阶段权重（用于计算总进度）
            "video": 0.40,       # 视频下载占40%
            "audio": 0.30,       # 音频下载占30%
            "merge": 0.30,       # FFmpeg合成占30%
        },
        "total_progress": 0,     # 🆕 总进度百分比 (0-100)
        "finished": False,
        "title": "",
        "url": "",
        "cid": "",
        "bvid": "",
    }
)


"""
视频导出（字幕硬嵌入）流程：

使用 ffmpeg 将字幕（ASS格式）硬嵌入到视频中
生成的视频保存到 work_dir/export_videos/
文件名格式：原视频名_burn.mp4
"""

export_queue: Queue[str] = Queue()
export_task_status = defaultdict(lambda: {
    "video_id": 0,
    "video_name": "",
    "subtitle_type": "raw",  # raw, translated, both
    "status": "Queued",  # Queued, Running, Completed, Failed
    "progress": 0,  # 进度百分比
    "output_filename": "",
    "error_message": "",
})


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
        task = download_status[task_id]

        # 更新状态
        task["stages"][stage] = status

        # 更新阶段进度
        if progress is not None:
            task["stage_progress"][stage] = min(100, max(0, progress))
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
        task["finished"] = all(
            s == "Completed" for s in task["stages"].values()
        )

from utils.stream_downloader.bili_download import get_direct_media_link,download_file_with_progress,merge_audio_video,get_video_info
from utils.stream_downloader.youtube_download import YouTubeDownloader
from .utils import format_duration
from utils.video_converter import VideoConverter
import requests
from yt_dlp import YoutubeDL

def download_thumbnail(thumbnail_url: str, md5_value: str) -> str:
    """下载缩略图并保存到本地，返回保存的文件路径"""
    if not thumbnail_url:
        return ''
    
    try:
        thumbnail_dir = os.path.join(settings.MEDIA_ROOT, 'thumbnail')
        os.makedirs(thumbnail_dir, exist_ok=True)
        
        # 获取文件扩展名，默认为jpg
        ext = thumbnail_url.split('.')[-1].lower() if '.' in thumbnail_url.split('/')[-1] else 'jpg'
        if ext not in ['jpg', 'jpeg', 'png', 'webp']:
            ext = 'jpg'
        
        thumbnail_filename = f"{md5_value}.{ext}"
        thumbnail_path = os.path.join(thumbnail_dir, thumbnail_filename)
        
        # 检查文件是否已存在
        if os.path.exists(thumbnail_path):
            return thumbnail_filename
        
        # 根据URL判断是B站还是YouTube，设置不同的headers
        if 'ytimg.com' in thumbnail_url or 'youtube.com' in thumbnail_url:
            # YouTube 缩略图
            headers = {
                'Referer': 'https://www.youtube.com',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            }
        else:
            # Bilibili 缩略图
            headers = {
                'Referer': 'https://www.bilibili.com',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            }
        
        resp = requests.get(thumbnail_url, headers=headers, timeout=30, stream=True)
        resp.raise_for_status()
        
        with open(thumbnail_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"Thumbnail downloaded: {thumbnail_filename}")
        return thumbnail_filename
        
    except Exception as e:
        print(f"Failed to download thumbnail: {e}")
        return ''

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
            
        thumbnail_url = video_info.get('thumbnail', '')
        duration_seconds = video_info.get('duration', 0)
        print(f"YouTube video info - Thumbnail: {thumbnail_url}, Duration: {duration_seconds}s")
    except Exception as e:
        print(f"Failed to get YouTube video info: {e}")
        dl_set(task_id, "video", "Failed")
        return
    
    # 创建临时工作目录
    work_dir = f"work_dir/{video_id}"
    os.makedirs(work_dir, exist_ok=True)
    
    try:
        # 下载视频到临时目录
        dl_set(task_id, "video", "Running")
        output_path = downloader.download_video(url, work_dir)
        if not output_path or not os.path.exists(output_path):
            dl_set(task_id, "video", "Failed")
            return
        dl_set(task_id, "video", "Completed")
        
        # YouTube 的 yt-dlp 通常会自动合并视频和音频
        # 所以我们跳过单独的音频下载和合并步骤
        dl_set(task_id, "audio", "Completed")
        dl_set(task_id, "merge", "Completed")
        
        # 创建保存视频的目录
        save_dir = os.path.join(settings.MEDIA_ROOT, 'saved_video')
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
            print("Download the same YouTube video, so skip.")
            return
        
        import shutil
        # 移动文件到最终位置
        shutil.move(output_path, file_path)
        
        # 下载并保存缩略图 (支持YouTube缩略图)
        thumbnail_filename = download_thumbnail(thumbnail_url, md5_value)
        
        # 格式化视频时长
        formatted_duration = format_duration(duration_seconds) if duration_seconds > 0 else None
        
        # 保存到Video数据库中
        Video.objects.create(
            name=title,
            url=f"{md5_value}.mp4",
            thumbnail_url=thumbnail_filename,
            video_length=formatted_duration,
            category=None,  # 临时分类，后续可以修改
        )
        print(f"YouTube video created with thumbnail: {thumbnail_filename}, duration: {formatted_duration}")
        
    except Exception as e:
        print(f"YouTube download error: {e}")
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
            print(f"Error cleaning up work directory: {e}")

def download_bilibili_video(task_id: str):
    with download_status_lock:
        task = download_status[task_id]
        bvid,cid, url, title =task["bvid"], task["cid"], task["url"], task["title"]
    
    # Read Bilibili sessdata from config using load_all_settings function
    try:
        settings_data = load_all_settings()
        sessdata = settings_data.get('Media Credentials', {}).get('bilibili_sessdata', '')
        print("sessdata:", sessdata)
    except Exception as e:
        print(f"Error loading settings: {e}")
        sessdata = ''  # fallback to empty string if there's an error
    
    # 获取视频基本信息，包括缩略图URL和时长
    try:
        video_info = get_video_info(bvid=bvid)
        thumbnail_url = video_info.get('pic_url', '')
        duration_seconds = video_info.get('duration', 0)
        print(f"Thumbnail URL: {thumbnail_url}")
        print(f"Video duration: {duration_seconds} seconds")
    except Exception as e:
        print(f"Failed to get video info: {e}")
        thumbnail_url = ''
        duration_seconds = 0
    
    video_file,audio_file,output_file,urls=get_direct_media_link(bvid,cid=cid,title=title,sessdata=sessdata)

    # 🆕 定义各阶段的进度回调
    def video_progress_cb(percent):
        dl_set(task_id, "video", "Running", progress=percent)

    def audio_progress_cb(percent):
        dl_set(task_id, "audio", "Running", progress=percent)

    def merge_progress_cb(percent):
        dl_set(task_id, "merge", "Running", progress=percent)

    # 1.下载视频流
    dl_set(task_id, "video", "Running")
    download_file_with_progress(urls['vidBaseUrl'], video_file, progress_callback=video_progress_cb)
    dl_set(task_id, "video", "Completed")

    # 2.下载音频流
    dl_set(task_id, "audio", "Running")
    download_file_with_progress(urls['audBaseUrl'], audio_file, progress_callback=audio_progress_cb)
    dl_set(task_id, "audio", "Completed")

    # ③ 合并音视频
    dl_set(task_id, "merge", "Running")
    merge_audio_video(audio_file, video_file, output_file, progress_callback=merge_progress_cb)
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
    save_dir = os.path.join(settings.MEDIA_ROOT, 'saved_video')
    os.makedirs(save_dir, exist_ok=True)
    # 计算文件的 MD5 值
    md5_hash = hashlib.md5()
    with open(output_file, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):   # 每次 8 KB
            md5_hash.update(chunk)
    md5_value = md5_hash.hexdigest()
    file_path = os.path.join(save_dir, f"{md5_value}.mp4")
    print("To be downloaded:",file_path)


    # 检查是否已经存在相同的文件
    existing_files = os.listdir(save_dir)
    file_exists = any(md5_value in fname for fname in existing_files)
    if file_exists:
        print("Download the same file from bilibili,so raise error.")
        return
    import shutil
    # 移动单个文件
    print("To be moved:",file_path)
    shutil.move(output_file, file_path)

    # 下载并保存缩略图
    thumbnail_filename = download_thumbnail(thumbnail_url, md5_value)
    
    # 格式化视频时长
    formatted_duration = format_duration(duration_seconds) if duration_seconds > 0 else None
    
    # 处理流程完成后不需要再次设置merge状态
    # 保存到Video数据库中
    Video.objects.create(
        name=title,
        url=f"{md5_value}.mp4",
        thumbnail_url=thumbnail_filename,  # 保存缩略图文件名
        video_length=formatted_duration,   # 保存视频时长
        category=None,     # temperaryly no,Can be set later
    )
    print(f"Video created with thumbnail: {thumbnail_filename}, duration: {formatted_duration}")

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
            'format': 'best[ext=m4a]/best[ext=mp3]/best',
            'outtmpl': f'{work_dir}/{title}.%(ext)s',
            'writeinfojson': False,  # 不保存元数据
        }
        
        # 获取音频信息包括缩略图
        info = None
        with YoutubeDL({'quiet': True, 'no_download': True}) as ydl:
            info = ydl.extract_info(url, download=False)
        
        if not info:
            dl_set(task_id, "video", "Failed")
            return
            
        thumbnail_url = info.get('thumbnail', '')
        duration_seconds = info.get('duration', 0)
        
        # 下载音频文件
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # 查找下载的音频文件
        downloaded_files = [f for f in os.listdir(work_dir) if f.endswith(('.m4a', '.mp3'))]
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
        save_dir = os.path.join(settings.MEDIA_ROOT, 'saved_audio')
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
            print("Download the same podcast audio, so skip.")
            return
        
        # 移动文件到最终位置
        import shutil
        shutil.move(audio_file, file_path)
        
        # 下载并保存缩略图
        thumbnail_filename = download_thumbnail(thumbnail_url, md5_value)
        
        # 格式化音频时长
        formatted_duration = format_duration(duration_seconds) if duration_seconds > 0 else None
        
        # 保存到Video数据库中（复用Video模型存储音频信息）
        Video.objects.create(
            name=title,
            url=f"{md5_value}{file_ext}",  # 保存带扩展名的文件名
            thumbnail_url=thumbnail_filename,
            video_length=formatted_duration,
            category=None,  # 使用不同的分类ID区分播客音频
        )
        print(f"Podcast audio created with thumbnail: {thumbnail_filename}, duration: {formatted_duration}, ext: {file_ext}")
        
    except Exception as e:
        print(f"Apple Podcast download error: {e}")
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
            print(f"Error cleaning up work directory: {e}")

def download_stream_media(task_id: str):
    """平台分发器：根据平台类型调用相应的下载函数"""
    with download_status_lock:
        task = download_status[task_id]
        platform = task.get("platform", "bilibili")  # 默认为bilibili以保持向后兼容
    
    print(f"Starting download for task {task_id}, platform: {platform}")
    
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
        download_stream_media(task_id) # 每个任务对应一个视频
    finally:
        download_queue.task_done()

def export_update_status(task_id: str, status: str, progress: int = 0, error_message: str = ""):
    """更新导出任务状态"""
    export_task_status[task_id]["status"] = status
    export_task_status[task_id]["progress"] = progress
    if error_message:
        export_task_status[task_id]["error_message"] = error_message

def get_video_bitrate(video_path: str) -> str:
    """使用 ffprobe 获取视频比特率"""
    import subprocess
    import json
    
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=bit_rate',
            '-of', 'json',
            video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if 'streams' in data and len(data['streams']) > 0:
                bit_rate = data['streams'][0].get('bit_rate')
                if bit_rate:
                    # Convert to k format (e.g., 1339k)
                    bit_rate_k = int(int(bit_rate) / 1000)
                    return f"{bit_rate_k}k"
        
        # Fallback: try to get format bitrate
        cmd_format = [
            'ffprobe',
            '-v', 'quiet',
            '-show_entries', 'format=bit_rate',
            '-of', 'json',
            video_path
        ]
        
        result = subprocess.run(cmd_format, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if 'format' in data:
                bit_rate = data['format'].get('bit_rate')
                if bit_rate:
                    bit_rate_k = int(int(bit_rate) / 1000)
                    return f"{bit_rate_k}k"
                    
        return "2000k"  # Default fallback bitrate
        
    except Exception as e:
        print(f"Error getting video bitrate: {e}")
        return "2000k"  # Default fallback bitrate

def export_video_with_subtitles(task_id: str):
    """导出带硬嵌入字幕的视频"""
    task = export_task_status[task_id]
    video_id = task["video_id"]
    subtitle_type = task["subtitle_type"]
    
    try:
        export_update_status(task_id, "Running", 5)
        
        # 获取视频信息
        video = Video.objects.get(pk=video_id)
        if not video:
            raise Exception('Video not found')
        
        video_path = os.path.join(settings.MEDIA_ROOT, 'saved_video', video.url)
        if not os.path.exists(video_path):
            raise Exception(f'Video file not found: {video_path}')
        
        # 检查字幕文件
        srt_dir = os.path.join('media', 'saved_srt')
        raw_srt_path = None
        trans_srt_path = None
        
        if video.srt_path:
            raw_srt_path = os.path.join(srt_dir, video.srt_path)
        if video.translated_srt_path:
            trans_srt_path = os.path.join(srt_dir, video.translated_srt_path)
        
        export_update_status(task_id, "Running", 10)
        
        # 根据字幕类型生成ASS文件
        temp_dir = 'work_dir/temp'
        os.makedirs(temp_dir, exist_ok=True)
        ass_filename = f"{task_id}.ass"
        ass_path = os.path.join(temp_dir, ass_filename)
        
        # 生成ASS字幕内容
        ass_content = generate_ass_content(video_id, subtitle_type, raw_srt_path, trans_srt_path)
        
        with open(ass_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        
        export_update_status(task_id, "Running", 30)
        
        # 获取视频比特率
        video_bitrate = get_video_bitrate(video_path)
        print(f"Video bitrate: {video_bitrate}")
        
        # 创建输出目录
        export_dir = 'work_dir/export_videos'
        os.makedirs(export_dir, exist_ok=True)
        
        # 生成输出文件名
        base_name = os.path.splitext(video.url)[0]  # 去掉扩展名
        output_filename = f"{base_name}_burn.mp4"
        output_path = os.path.join(export_dir, output_filename)
        
        export_update_status(task_id, "Running", 40)
        
        # FFmpeg 命令
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vf', f'ass={ass_path}',
            '-c:a', 'copy',  # 保持音频不变
            '-b:v', video_bitrate,  # 使用原视频的比特率
            '-y',  # 覆盖输出文件
            output_path
        ]
        
        print(f"FFmpeg command: {' '.join(ffmpeg_cmd)}")
        
        # 执行FFmpeg命令
        import subprocess
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 模拟进度更新（实际情况下可以解析FFmpeg输出获取真实进度）
        import threading
        import time
        
        def update_progress():
            progress = 40
            while process.poll() is None and progress < 90:
                time.sleep(2)
                progress += 5
                export_update_status(task_id, "Running", min(progress, 90))
        
        progress_thread = threading.Thread(target=update_progress)
        progress_thread.start()
        
        # 等待FFmpeg完成
        stdout, stderr = process.communicate(timeout=1800)  # 30分钟超时
        progress_thread.join()
        
        if process.returncode != 0:
            raise Exception(f"FFmpeg failed: {stderr}")
        
        # 检查输出文件是否存在
        if not os.path.exists(output_path):
            raise Exception("Output video file was not created")
        
        # 更新任务状态
        export_task_status[task_id]["output_filename"] = output_filename
        export_update_status(task_id, "Completed", 100)
        
        print(f"Video export completed: {output_path}")
        
    except Exception as exc:
        error_msg = str(exc)
        print(f"视频导出失败: {error_msg}")
        export_update_status(task_id, "Failed", 0, error_msg)
    finally:
        # 清理临时ASS文件
        try:
            if 'ass_path' in locals() and os.path.exists(ass_path):
                os.remove(ass_path)
        except:
            pass

def generate_ass_content(video_id: int, subtitle_type: str, raw_srt_path: str = None, trans_srt_path: str = None) -> str:
    """生成ASS字幕内容"""
    from utils.split_subtitle.ASRData import from_srt
    from .views.set_setting import load_all_settings
    
    # 加载字幕设置
    try:
        settings_data = load_all_settings()
        raw_settings = settings_data.get('Subtitle settings', {})
        foreign_settings = settings_data.get('Foreign Subtitle settings', {})
        
        # 合并设置，使用snake_case命名
        subtitle_settings = {
            # Raw subtitle settings
            'font_family': raw_settings.get('font_family', '宋体'),
            'font_size': int(raw_settings.get('font_size', 18)),
            'font_color': raw_settings.get('font_color', '#ea9749'),
            'font_weight': raw_settings.get('font_weight', '400'),
            'background_color': raw_settings.get('background_color', '#000000'),
            'background_style': raw_settings.get('background_style', 'semi-transparent'),
            'border_radius': int(raw_settings.get('border_radius', 4)),
            'text_shadow': raw_settings.get('text_shadow', 'false').lower() == 'true',
            'text_stroke': raw_settings.get('text_stroke', 'false').lower() == 'true',
            'text_stroke_color': raw_settings.get('text_stroke_color', '#000000'),
            'text_stroke_width': int(raw_settings.get('text_stroke_width', 2)),
            'bottom_distance': int(raw_settings.get('bottom_distance', 80)),
            # Foreign subtitle settings
            'foreign_font_family': foreign_settings.get('foreign_font_family', 'Arial'),
            'foreign_font_size': int(foreign_settings.get('foreign_font_size', 16)),
            'foreign_font_color': foreign_settings.get('foreign_font_color', '#ffffff'),
            'foreign_font_weight': foreign_settings.get('foreign_font_weight', '400'),
            'foreign_background_color': foreign_settings.get('foreign_background_color', '#000000'),
            'foreign_background_style': foreign_settings.get('foreign_background_style', 'semi-transparent'),
            'foreign_border_radius': int(foreign_settings.get('foreign_border_radius', 4)),
            'foreign_text_shadow': foreign_settings.get('foreign_text_shadow', 'false').lower() == 'true',
            'foreign_text_stroke': foreign_settings.get('foreign_text_stroke', 'false').lower() == 'true',
            'foreign_text_stroke_color': foreign_settings.get('foreign_text_stroke_color', '#000000'),
            'foreign_text_stroke_width': int(foreign_settings.get('foreign_text_stroke_width', 2)),
            'foreign_bottom_distance': int(foreign_settings.get('foreign_bottom_distance', 120)),
        }
    except:
        # 默认设置使用snake_case
        subtitle_settings = {
            'font_family': '宋体',
            'font_size': 18,
            'font_color': '#ea9749',
            'font_weight': '400',
            'background_color': '#000000',
            'background_style': 'semi-transparent',
            'border_radius': 4,
            'text_shadow': False,
            'text_stroke': False,
            'text_stroke_color': '#000000',
            'text_stroke_width': 2,
            'bottom_distance': 80,
            'foreign_font_family': 'Arial',
            'foreign_font_size': 16,
            'foreign_font_color': '#ffffff',
            'foreign_font_weight': '400',
            'foreign_background_color': '#000000',
            'foreign_background_style': 'semi-transparent',
            'foreign_border_radius': 4,
            'foreign_text_shadow': False,
            'foreign_text_stroke': False,
            'foreign_text_stroke_color': '#000000',
            'foreign_text_stroke_width': 2,
            'foreign_bottom_distance': 120,
        }
    
    # 转换颜色格式（从hex到ASS格式）
    def hex_to_ass_color(hex_color: str) -> str:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        return f"&H00{b:02X}{g:02X}{r:02X}"
    
    # 格式化时间为ASS格式
    def format_ass_time(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centisecs = int((seconds % 1) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"
    
    # ASS文件头部（获取实际视频分辨率信息以确保正确缩放）
    video = Video.objects.get(pk=video_id)
    
    # 获取视频实际分辨率
    width, height = 1920, 1080  # 默认分辨率
    try:
        from .views.videos import get_media_path_info, is_audio_file
        import subprocess
        import json as json_lib
        
        # 对于音频文件使用默认分辨率
        if not is_audio_file(video.url):
            directory_name, _ = get_media_path_info(video.url)
            video_path = os.path.join(settings.MEDIA_ROOT, directory_name, video.url)
            
            if os.path.exists(video_path):
                # 使用 ffprobe 获取视频分辨率
                cmd = [
                    'ffprobe',
                    '-v', 'quiet',
                    '-select_streams', 'v:0',
                    '-show_entries', 'stream=width,height',
                    '-of', 'json',
                    video_path
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    data = json_lib.loads(result.stdout)
                    if 'streams' in data and len(data['streams']) > 0:
                        stream = data['streams'][0]
                        width = stream.get('width', 1920)
                        height = stream.get('height', 1080)
                        print(f"Got video dimensions: {width}x{height}")
    except Exception as e:
        print(f"Failed to get video dimensions: {e}, using default 1920x1080")
    
    ass_content = f"""[Script Info]
Title: {video.name}
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
"""
    
    # 添加样式
    if subtitle_type in ['raw', 'both']:
        raw_color = hex_to_ass_color(subtitle_settings.get('font_color', '#ea9749'))
        raw_bg_color = hex_to_ass_color(subtitle_settings.get('background_color', '#000000'))
        raw_font_size = subtitle_settings.get('font_size', 18)
        raw_bold = -1 if int(subtitle_settings.get('font_weight', 400)) > 500 else 0
        raw_shadow = 2 if subtitle_settings.get('text_shadow', False) else 0
        raw_margin_v = subtitle_settings.get('bottom_distance', 80)
        
        # Add text stroke (outline) support for raw subtitles
        raw_outline = subtitle_settings.get('text_stroke_width', 2) if subtitle_settings.get('text_stroke', False) else 0
        raw_outline_color = hex_to_ass_color(subtitle_settings.get('text_stroke_color', '#000000')) if subtitle_settings.get('text_stroke', False) else '&H00000000'
        
        ass_content += f"Style: Raw,{subtitle_settings.get('font_family', '宋体')},{raw_font_size},{raw_color},{raw_color},{raw_outline_color},{raw_bg_color},{raw_bold},0,0,0,100,100,0,0,1,{raw_outline},{raw_shadow},2,0,0,{raw_margin_v},1\n"
    
    if subtitle_type in ['translated', 'both']:
        trans_color = hex_to_ass_color(subtitle_settings.get('foreign_font_color', '#ffffff'))
        trans_bg_color = hex_to_ass_color(subtitle_settings.get('foreign_background_color', '#000000'))
        trans_font_size = subtitle_settings.get('foreign_font_size', 16)
        trans_bold = -1 if int(subtitle_settings.get('foreign_font_weight', 400)) > 500 else 0
        trans_shadow = 2 if subtitle_settings.get('foreign_text_shadow', False) else 0
        trans_margin_v = subtitle_settings.get('foreign_bottom_distance', 120)
        
        # Add text stroke (outline) support for foreign subtitles
        trans_outline = subtitle_settings.get('foreign_text_stroke_width', 2) if subtitle_settings.get('foreign_text_stroke', False) else 0
        trans_outline_color = hex_to_ass_color(subtitle_settings.get('foreign_text_stroke_color', '#000000')) if subtitle_settings.get('foreign_text_stroke', False) else '&H00000000'
        
        ass_content += f"Style: Foreign,{subtitle_settings.get('foreign_font_family', 'Arial')},{trans_font_size},{trans_color},{trans_color},{trans_outline_color},{trans_bg_color},{trans_bold},0,0,0,100,100,0,0,1,{trans_outline},{trans_shadow},2,0,0,{trans_margin_v},1\n"
    
    ass_content += """
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    # 加载字幕文件并生成对话行
    raw_asr_data = None
    trans_asr_data = None
    
    if raw_srt_path and os.path.exists(raw_srt_path):
        with open(raw_srt_path, 'r', encoding='utf-8') as f:
            raw_asr_data = from_srt(f.read())
    
    if trans_srt_path and os.path.exists(trans_srt_path):
        with open(trans_srt_path, 'r', encoding='utf-8') as f:
            trans_asr_data = from_srt(f.read())
    
    # 合并字幕（使用原文字幕的时间戳）
    if raw_asr_data and raw_asr_data.has_data():
        for i, raw_seg in enumerate(raw_asr_data.segments):
            # 转换时间戳（从毫秒到秒）
            start_time = format_ass_time(raw_seg.start_time / 1000.0)
            end_time = format_ass_time(raw_seg.end_time / 1000.0)
            
            if subtitle_type == 'raw':
                ass_content += f"Dialogue: 0,{start_time},{end_time},Raw,,0,0,0,,{raw_seg.text}\n"
            elif subtitle_type == 'translated':
                if trans_asr_data and i < len(trans_asr_data.segments):
                    trans_text = trans_asr_data.segments[i].text
                else:
                    trans_text = raw_seg.text
                ass_content += f"Dialogue: 0,{start_time},{end_time},Foreign,,0,0,0,,{trans_text}\n"
            elif subtitle_type == 'both':
                ass_content += f"Dialogue: 0,{start_time},{end_time},Raw,,0,0,0,,{raw_seg.text}\n"
                if trans_asr_data and i < len(trans_asr_data.segments):
                    ass_content += f"Dialogue: 0,{start_time},{end_time},Foreign,,0,0,0,,{trans_asr_data.segments[i].text}\n"
    
    return ass_content

def process_export_task() -> None:
    """被后台线程循环调用处理导出任务"""
    try:
        task_id = export_queue.get_nowait()
    except Empty:
        return

    try:
        export_video_with_subtitles(task_id)
    finally:
        export_queue.task_done()

def generate_tts_audio(task_id: str) -> None:
    """
    TTS配音生成任务处理函数

    从字幕文件生成配音音频，并与原视频合成
    """
    task = tts_task_status[task_id]

    try:
        task["status"] = "Running"
        task["progress"] = 5

        video_id = task["video_id"]
        language = task["language"]
        voice = task["voice"]

        # 获取字幕文件路径
        srt_filename = f"{video_id}_{language}.srt"
        srt_path = os.path.join('media/saved_srt', srt_filename)

        if not os.path.exists(srt_path):
            raise FileNotFoundError(f"Subtitle file not found: {srt_path}")

        print(f"[TTS] Starting audio generation for task {task_id}")
        print(f"[TTS] SRT file: {srt_path}, Voice: {voice}")

        # 获取API密钥和配置
        from .views.set_setting import load_all_settings
        settings_data = load_all_settings()
        tts_settings = settings_data.get('TTS settings', {})

        api_key = tts_settings.get('dashscope_api_key', '')
        if not api_key:
            raise ValueError("DashScope API key not configured")

        # 加载TTS配置参数
        max_retries = int(tts_settings.get('max_retries', '5'))
        enable_checkpointing = tts_settings.get('enable_checkpointing', 'true').lower() == 'true'

        print(f"[TTS] Config: max_retries={max_retries}, checkpointing={enable_checkpointing}")

        # 创建输出目录
        tts_output_dir = 'work_dir/tts_output'
        os.makedirs(tts_output_dir, exist_ok=True)

        # 生成临时音频文件
        temp_audio_path = os.path.join(tts_output_dir, f"{task_id}_temp.wav")

        # 进度回调
        def progress_callback(completed: int, total: int):
            task["total_segments"] = total
            task["completed_segments"] = completed
            # 进度从5%到85%（留15%给视频合成）
            progress = 5 + int((completed / total) * 80)
            task["progress"] = progress
            print(f"[TTS] Progress: {completed}/{total} segments ({progress}%)")

        # 调用TTS生成器（带重试和检查点支持）
        from utils.tts.tts_generator import synthesize_audio_from_srt

        task["progress"] = 10
        segment_count, duration_ms = synthesize_audio_from_srt(
            srt_path=srt_path,
            output_wav=temp_audio_path,
            api_key=api_key,
            voice=voice,
            progress_callback=progress_callback,
            task_id=task_id,
            enable_checkpointing=enable_checkpointing,
            max_retries_per_segment=max_retries
        )

        print(f"[TTS] Audio generation completed: {segment_count} segments, {duration_ms}ms")
        task["progress"] = 85

        # 获取原视频
        video = Video.objects.get(pk=video_id)
        from .views.videos import get_media_path_info
        directory_name, _ = get_media_path_info(video.url)
        video_path = os.path.join(settings.MEDIA_ROOT, directory_name, video.url)

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Original video not found: {video_path}")

        # 合成音频和视频
        import subprocess

        # 生成输出文件名
        output_filename = f"{os.path.splitext(video.url)[0]}_{language}.mp4"
        output_path = os.path.join(tts_output_dir, output_filename)

        # FFmpeg命令：替换视频的音频轨道
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', video_path,          # 输入视频
            '-i', temp_audio_path,     # 输入音频
            '-c:v', 'copy',            # 复制视频流（不重新编码）
            '-map', '0:v:0',           # 使用第一个输入的视频
            '-map', '1:a:0',           # 使用第二个输入的音频
            '-c:a', 'aac',             # 音频编码为AAC
            '-b:a', '192k',            # 音频比特率
            '-shortest',               # 以最短的流为准
            '-y',                      # 覆盖输出文件
            output_path
        ]

        print(f"[TTS] Merging audio with video: {' '.join(ffmpeg_cmd)}")
        task["progress"] = 90

        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10分钟超时
        )

        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg merge failed: {result.stderr}")

        # 检查输出文件
        if not os.path.exists(output_path):
            raise RuntimeError("Output video file was not created")

        # 清理临时音频文件
        try:
            os.remove(temp_audio_path)
        except:
            pass

        # 更新任务状态
        task["status"] = "Completed"
        task["progress"] = 100
        task["output_file"] = output_filename

        print(f"[TTS] Task completed: {task_id}, output: {output_filename}")

    except Exception as exc:
        error_msg = str(exc)
        print(f"[TTS] Task failed: {task_id}, error: {error_msg}")
        task["status"] = "Failed"
        task["error_message"] = error_msg

def process_tts_task() -> None:
    """被后台线程循环调用处理TTS任务"""
    try:
        task_id = tts_queue.get_nowait()
    except Empty:
        return

    try:
        generate_tts_audio(task_id)
    finally:
        tts_queue.task_done()