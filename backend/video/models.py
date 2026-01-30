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
        ordering = ("id",)  # 按需要


class Collection(models.Model):
    """
    一组视频的集合，如“Python 入门系列”“2024 年春招宣讲会”等。
    """

    name = models.CharField(max_length=128, unique=True)
    category = models.ForeignKey(
        Category,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,  # 删除合集时对应视频的Category外键设置为空，不删除。
        related_name="collections",
    )
    created_time = models.DateTimeField(auto_now_add=True)
    thumbnail_url = models.CharField(max_length=128, blank=True, null=True)
    last_modified = models.DateTimeField(
        verbose_name="最后打开时间",
        default=timezone.now,  # 默认值为当前时间
        # auto_now=True,  # 每次保存时自动更新（但无法手动控制）
    )

    class Meta:
        db_table = "collection"
        verbose_name = "合集"
        verbose_name_plural = "合集"
        ordering = ("-created_time",)

    def __str__(self):
        return self.name


class VideoAttachment(models.Model):
    """笔记和思维导图的统一附件模型"""

    video = models.ForeignKey(
        "Video", on_delete=models.CASCADE, related_name="attachments"
    )

    # 文件信息
    filename = models.CharField(max_length=255, help_text="生成的存储文件名")
    original_name = models.CharField(max_length=255, help_text="用户原始文件名")
    file_path = models.CharField(max_length=500, help_text="相对于MEDIA_ROOT的路径")
    file_type = models.CharField(max_length=50, help_text="MIME类型，如'image/jpeg'")
    file_size = models.IntegerField(help_text="文件大小（字节）")

    # 使用上下文
    context_type = models.CharField(
        max_length=20,
        choices=[("notes", "Notes"), ("mindmap", "Mindmap")],
        help_text="此附件的使用位置",
    )
    context_id = models.CharField(
        max_length=100, blank=True, help_text="在思维导图中使用时的节点ID"
    )

    # 元数据
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
        """返回此附件的URL路径"""
        return f"/media/{self.file_path}"

    def delete_file(self):
        """从存储中删除物理文件"""
        try:
            full_path = os.path.join(settings.MEDIA_ROOT, self.file_path)
            if os.path.exists(full_path):
                os.remove(full_path)
                return True
        except Exception as e:
            print(f"删除文件错误 {self.file_path}: {e}")
        return False


class Video(models.Model):
    name = models.CharField(max_length=128)
    url = models.CharField(max_length=128, blank=True, null=True)
    thumbnail_url = models.CharField(max_length=128, blank=True, null=True)
    srt_path = models.CharField(max_length=128, blank=True, null=True)
    translated_srt_path = models.CharField(
        max_length=128, blank=True, null=True, help_text="翻译字幕文件路径"
    )
    created_time = models.DateTimeField(blank=True, null=True)
    video_length = models.CharField(max_length=128, blank=True, null=True)
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
    tags = models.JSONField(
        blank=True,
        null=True,
        default=list,
        help_text="标签列表，如['tools', 'afternoon', 'tutorial']",
    )

    last_modified = models.DateTimeField(
        verbose_name="最后打开时间",
        default=timezone.now,  # 默认值为当前时间
        # auto_now=True,  # 每次保存时自动更新（但无法手动控制）
    )

    def __str__(self):
        # 选择能快速识别对象的字段
        return f"{self.name} (id={self.pk})"

    class Meta:
        db_table = "video"


@receiver(pre_delete, sender=Video)
def delete_video_files(sender, instance, **kwargs):  # pylint: disable=unused-argument
    """
    在删除Video对象前，删除相关的缩略图文件
    这确保了无论通过什么方式删除Video对象，缩略图都会被清理
    """
    if instance.thumbnail_url:
        try:
            thumbnail_dir = os.path.join(settings.MEDIA_ROOT, "thumbnail")
            thumbnail_path = os.path.join(thumbnail_dir, instance.thumbnail_url)

            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
                print(f"信号：已删除缩略图 {instance.thumbnail_url}")
        except Exception as e:
            print(f"信号：删除缩略图失败 {instance.thumbnail_url}: {e}")
