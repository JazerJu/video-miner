"""按 id 删除视频，走和 /api/videos/batch_action 完全相同的代码路径。

那个接口是普通 Django View，只认 session，命令行拿 DRF token 过不去（会变成
AnonymousUser）。这个命令直接在服务端跑，省掉登录，行为与接口一致：
先 delete_all_related_files(video) 再 video.delete()。

删除不可逆，所以默认只打印不动手，要真删必须显式加 --yes。
"""
from django.core.management.base import BaseCommand

from video.models import Video
from video.views.videos import delete_all_related_files


class Command(BaseCommand):
    help = "按 id 删除视频及其关联文件（与 batch_action delete 等价）"

    def add_arguments(self, parser):
        parser.add_argument("ids", nargs="+", type=int, help="要删除的 video id")
        parser.add_argument("--yes", action="store_true", help="真的删除；不加则只预演")

    def handle(self, *args, **options):
        ids, really = options["ids"], options["yes"]
        videos = {v.id: v for v in Video.objects.filter(pk__in=ids)}
        missing = [i for i in ids if i not in videos]
        if missing:
            self.stdout.write(self.style.WARNING(f"这些 id 不存在，已跳过: {missing}"))

        deleted = failed = 0
        for vid in ids:
            video = videos.get(vid)
            if video is None:
                continue
            name = video.name
            if not really:
                self.stdout.write(f"  [预演] 会删除 id={vid} {name}")
                deleted += 1
                continue
            try:
                files, errors = delete_all_related_files(video)
                video.delete()
                deleted += 1
                self.stdout.write(f"  已删除 id={vid} ({len(files)} 个文件) {name}")
                for err in errors:
                    self.stdout.write(self.style.WARNING(f"    文件删除告警: {err}"))
            except Exception as exc:
                failed += 1
                self.stdout.write(self.style.ERROR(f"  id={vid} 删除失败: {exc}"))

        self.stdout.write(self.style.SUCCESS(
            f"{'已删除' if really else '预演将删除'} {deleted} 条；失败 {failed}；剩余视频 {Video.objects.count()} 条"
        ))
        if not really:
            self.stdout.write(self.style.NOTICE("这是预演。确认无误后加 --yes 真正执行。"))
