"""
批量更新视频文件信息的管理命令。
用于初始化现有视频的文件大小、创建时间和时长秒数字段。
"""

from django.core.management.base import BaseCommand
from video.utils import batch_update_video_file_info


class Command(BaseCommand):
    help = "批量更新所有视频的文件信息（文件大小、创建时间、时长秒数）"

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("开始批量更新视频文件信息..."))

        updated_count, error_count = batch_update_video_file_info()

        if updated_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f"成功更新 {updated_count} 个视频的信息")
            )

        if error_count > 0:
            self.stdout.write(self.style.WARNING(f"{error_count} 个视频更新失败"))

        if updated_count == 0 and error_count == 0:
            self.stdout.write(self.style.NOTICE("没有需要更新的视频"))
