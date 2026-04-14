from django.db import migrations, models
from django.utils import timezone


def backfill_video_timestamps(apps, schema_editor):
    Video = apps.get_model("video", "Video")

    for video in Video.objects.all().iterator():
        updates = []

        if not getattr(video, "created_at", None):
            video.created_at = (
                video.file_created_time
                or video.last_modified
                or timezone.now()
            )
            updates.append("created_at")

        if (
            not getattr(video, "content_updated_at", None)
            and (
                video.notes
                or video.srt_path
                or video.translated_srt_path
                or video.chapters
            )
        ):
            video.content_updated_at = video.last_modified or timezone.now()
            updates.append("content_updated_at")

        if updates:
            video.save(update_fields=updates)


class Migration(migrations.Migration):
    dependencies = [
        ("video", "0002_add_source_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="video",
            name="content_updated_at",
            field=models.DateTimeField(
                blank=True,
                help_text="字幕/笔记最近修改时间",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="video",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                blank=True,
                help_text="视频加入 VidGo 项目的时间",
                null=True,
            ),
        ),
        migrations.RunPython(backfill_video_timestamps, migrations.RunPython.noop),
    ]
