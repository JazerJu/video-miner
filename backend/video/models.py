from django.db import models
from django.utils import timezone
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.conf import settings
import os


class Category(models.Model):
    name = models.CharField(max_length=128, unique=True)
    created_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "category"
        verbose_name = "分类"
        verbose_name_plural = "分类"
        ordering = ("id",)

    def __str__(self):
        return self.name


class Tag(models.Model):
    """标签模型，用于管理标签的元数据（颜色、名称等）"""

    name = models.CharField(max_length=64, unique=True, help_text="标签名称")
    color = models.CharField(
        max_length=7, default="#3B82F6", help_text="标签颜色（十六进制）"
    )

    class Meta:
        db_table = "tag"
        verbose_name = "标签"
        verbose_name_plural = "标签"
        ordering = ("name",)

    def __str__(self):
        return self.name


class Video(models.Model):
    name = models.CharField(max_length=128)
    url = models.CharField(max_length=128, blank=True, null=True)
    thumbnail_url = models.CharField(max_length=128, blank=True, null=True)
    srt_path = models.CharField(max_length=128, blank=True, null=True)
    translated_srt_path = models.CharField(
        max_length=128, blank=True, null=True, help_text="翻译字幕文件路径"
    )
    video_length = models.CharField(max_length=128, blank=True, null=True)

    # 用于排序的数值字段（从文件系统获取，不每次请求都计算）
    file_size = models.BigIntegerField(
        blank=True, null=True, help_text="文件大小（字节）"
    )
    video_length_seconds = models.FloatField(
        blank=True, null=True, help_text="视频时长（秒），用于排序"
    )
    file_created_time = models.DateTimeField(
        blank=True, null=True, help_text="文件创建时间（从文件系统获取）"
    )
    category = models.ForeignKey(
        Category,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="categories",
    )

    description = models.TextField(blank=True, null=True)
    chapters = models.JSONField(
        blank=True, null=True, default=list, help_text="视频章节信息，JSON格式存储"
    )
    notes = models.TextField(
        blank=True,
        null=True,
        max_length=8000,
        help_text="视频笔记，Markdown格式，限制8000字符",
    )

    # 新字段
    video_source = models.CharField(
        max_length=20,
        choices=[
            ("bilibili", "Bilibili"),
            ("youtube", "YouTube"),
            ("ar_glass", "AR Glass"),
            ("upload", "Upload"),
        ],
        blank=True,
        null=True,
        help_text="视频来源",
    )
    raw_lang = models.CharField(
        max_length=5,
        choices=[
            ("en", "English"),
            ("zh", "Chinese"),
            ("jp", "Japanese"),
        ],
        blank=True,
        null=True,
        help_text="视频原始语言",
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="videos",
        help_text="视频标签",
    )

    last_modified = models.DateTimeField(
        verbose_name="最后打开时间",
        default=timezone.now,
    )

    last_played_time = models.FloatField(
        default=0.0,
        verbose_name="上次播放时间（秒）",
        help_text="记录视频上次播放到的秒数",
    )

    def __str__(self):
        return f"{self.name} (id={self.pk})"

    @property
    def duration_for_sort(self):
        """
        返回用于排序的视频时长（秒）
        优先使用 video_length_seconds 字段，如果没有则尝试从 video_length 文本解析
        """
        if self.video_length_seconds is not None:
            return self.video_length_seconds

        # 尝试从 video_length 文本格式 (HH:MM:SS) 解析
        if self.video_length:
            try:
                parts = self.video_length.split(":")
                if len(parts) == 3:
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    seconds = int(parts[2])
                    return hours * 3600 + minutes * 60 + seconds
            except (ValueError, IndexError):
                pass

        return 0

    class Meta:
        db_table = "video"


class VideoAttachment(models.Model):
    video = models.ForeignKey(
        Video, on_delete=models.CASCADE, related_name="attachments"
    )
    filename = models.CharField(max_length=255, help_text="生成的存储文件名")
    original_name = models.CharField(max_length=255, help_text="用户原始文件名")
    file_path = models.CharField(max_length=500, help_text="相对于MEDIA_ROOT的路径")
    file_type = models.CharField(max_length=50, help_text="MIME类型，如'image/jpeg'")
    file_size = models.IntegerField(help_text="文件大小（字节）")
    context_type = models.CharField(
        max_length=20,
        choices=[("notes", "Notes"), ("mindmap", "Mindmap")],
        help_text="此附件的使用位置",
    )
    context_id = models.CharField(
        max_length=100, blank=True, help_text="在思维导图中使用时的节点ID"
    )
    alt_text = models.CharField(
        max_length=255, blank=True, help_text="可访问性的替代文本"
    )
    upload_time = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True, help_text="软删除时设为False")

    class Meta:
        db_table = "video_attachment"
        indexes = [
            models.Index(fields=["video", "context_type"]),
            models.Index(fields=["video", "context_id"]),
        ]
        ordering = ["-upload_time"]

    def __str__(self):
        return f"{self.original_name} ({self.context_type}) for {self.video.name}"

    @property
    def url(self):
        return f"/media/{self.file_path}"

    def delete_file(self):
        try:
            full_path = os.path.join(settings.MEDIA_ROOT, self.file_path)
            if os.path.exists(full_path):
                os.remove(full_path)
                return True
        except Exception as e:
            print(f"删除文件错误 {self.file_path}: {e}")
        return False


@receiver(pre_delete, sender=Video)
def delete_video_files(sender, instance, **kwargs):
    if instance.thumbnail_url:
        try:
            thumbnail_dir = os.path.join(settings.MEDIA_ROOT, "thumbnail")
            thumbnail_path = os.path.join(thumbnail_dir, instance.thumbnail_url)

            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
                print(f"信号：已删除缩略图 {instance.thumbnail_url}")
        except Exception as e:
            print(f"信号：删除缩略图失败 {instance.thumbnail_url}: {e}")
