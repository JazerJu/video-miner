from django.utils import timezone
from django.conf import settings
import ffmpeg
import os


def get_video_duration(file_path):
    """使用ffmpeg获取视频时长(秒)"""
    if not os.path.exists(file_path):
        return None

    try:
        probe = ffmpeg.probe(file_path)
        duration = float(probe["format"]["duration"])
        return duration
    except Exception as e:
        print(f"Failed to get duration for {file_path}: {str(e)}")
        return None


def format_duration(seconds):
    """将秒数转换为 HH:MM:SS 格式"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def update_video_length(video):
    """更新单个视频的时长信息"""
    if not video.url:
        return None

    video_path = os.path.join(settings.MEDIA_ROOT, "saved_video", video.url)
    duration = get_video_duration(video_path)

    if duration is not None:
        formatted_duration = format_duration(duration)
        video.video_length = formatted_duration
        video.save(update_fields=["video_length"])
        return formatted_duration
    return None


def calc_diff_time(start_time):
    # 计算视频最后一次打开时间与当前时间的差值。
    # 并按照分钟为单位，如果小于1分钟，返回一分钟内；小于1小时返回一小时内；小于1天返回一天内
    # 否则返回大于1天
    now = timezone.now()
    diff = now - start_time
    if diff.total_seconds() < 60:
        return "一分钟内"
    elif diff.total_seconds() < 3600:
        return "一小时内"
    elif diff.total_seconds() < 86400:
        return "一天内"
    elif diff.total_seconds() < 86400 * 7:
        days = diff.days
        return f"{days}天内"
    else:
        return "大于一周"


def update_video_file_info(video, save=True):
    """
    从文件系统获取视频的元数据信息并更新到数据库
    获取: 文件大小、文件创建时间、视频时长(秒)

    Args:
        video: Video 模型实例
        save: 是否立即保存到数据库（默认True）

    Returns:
        dict: 包含更新后的字段值，或 None 如果文件不存在
    """
    if not video.url:
        return None

    # 构建文件路径（支持 saved_video 和 saved_audio 目录）
    from .services.audio_processing import is_audio_file

    if is_audio_file(video.url):
        file_path = os.path.join(settings.MEDIA_ROOT, "saved_audio", video.url)
    else:
        file_path = os.path.join(settings.MEDIA_ROOT, "saved_video", video.url)

    if not os.path.exists(file_path):
        print(f"[WARN] File not found: {file_path}")
        return None

    try:
        # 获取文件大小（字节）
        file_size = os.path.getsize(file_path)

        # 获取文件创建时间（Linux 使用 st_ctime，Windows 使用 st_ctime 或 st_birthtime）
        stat_info = os.stat(file_path)
        file_created_timestamp = getattr(stat_info, "st_birthtime", stat_info.st_ctime)
        file_created_time = timezone.datetime.fromtimestamp(
            file_created_timestamp, tz=timezone.utc
        )

        # 获取视频时长（秒）
        duration_seconds = get_video_duration(file_path)

        # 更新视频实例
        video.file_size = file_size
        video.file_created_time = file_created_time

        if duration_seconds is not None:
            video.video_length_seconds = duration_seconds
            # 同时更新文本格式的 video_length
            video.video_length = format_duration(duration_seconds)

        if save:
            video.save(
                update_fields=[
                    "file_size",
                    "file_created_time",
                    "video_length_seconds",
                    "video_length",
                ]
            )

        return {
            "file_size": file_size,
            "file_created_time": file_created_time,
            "video_length_seconds": duration_seconds,
            "video_length": video.video_length if duration_seconds else None,
        }

    except Exception as e:
        print(f"[ERROR] Failed to update file info for {video.name}: {e}")
        return None


def batch_update_video_file_info():
    """
    批量更新所有视频的文件信息
    用于初始化或后台任务
    """
    from .models import Video

    videos = Video.objects.all()
    updated_count = 0
    error_count = 0

    print(f"[INFO] Starting batch update for {videos.count()} videos...")

    for video in videos:
        result = update_video_file_info(video, save=True)
        if result:
            updated_count += 1
            print(
                f"[OK] Updated: {video.name} - Size: {result['file_size']} bytes, "
                f"Duration: {result['video_length_seconds']}s"
            )
        else:
            error_count += 1

    print(
        f"[INFO] Batch update complete: {updated_count} updated, {error_count} errors"
    )
    return updated_count, error_count
