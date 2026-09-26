"""给已下载的 B 站视频补抓站内中文字幕和 UP 主章节，不重新下载视频。

下载时才会走 _apply_bilibili_metadata()，所以在字幕抓取上线之前下的视频没有字幕。
Video 表不存 cid，靠「标题 → pagelist 的 part 名」反查：记录名形如
"<前缀>-p<N>-<part 名>"，而其中的 p<N> 在不同批次里编号不一致（老批次差 1），
所以只按 part 名匹配，不用 p 号。
"""
import re

from django.conf import settings
from django.core.management.base import BaseCommand

from utils.stream_downloader import native_subtitles
from utils.stream_downloader.bili_download import (
    get_cid,
    get_player_v2,
    get_subtitle_body,
)
from video.models import Video
from video.tasks import _store_native_metadata
from video.views.set_setting import load_all_settings


def _norm(text):
    """Part names differ between batches only by punctuation and spacing."""
    return re.sub(r"[\s_\-–—、,，.。:：+＋]", "", text or "").lower()


class Command(BaseCommand):
    help = "为已下载的 B 站视频补抓中文字幕和章节（不重新下载视频）"

    def add_arguments(self, parser):
        parser.add_argument("--bvid", required=True, help="要回填的稿件 bvid")
        parser.add_argument("--dry-run", action="store_true", help="只打印会做什么，不写库")
        parser.add_argument("--force", action="store_true", help="已有 srt_path 的记录也重新抓")

    def handle(self, *args, **options):
        bvid, dry, force = options["bvid"], options["dry_run"], options["force"]
        sessdata = load_all_settings().get("Media Credentials", {}).get("bilibili_sessdata", "")
        if not sessdata:
            self.stdout.write(self.style.ERROR("没有配置 bilibili_sessdata，字幕列表会是空的"))
            return

        _, pages = get_cid(bvid=bvid)
        by_part = {_norm(p["part"]): p for p in pages}
        videos = Video.objects.filter(source_url__contains=bvid, video_source="bilibili")
        self.stdout.write(f"{bvid}: 源 {len(pages)} 个分P，库中 {videos.count()} 条记录")

        done = skipped = unmatched = nosub = failed = 0
        for video in videos.order_by("id"):
            if video.srt_path and not force:
                skipped += 1
                continue
            tail = (video.name or "").split("-", 2)[-1]
            page = by_part.get(_norm(tail))
            if page is None:
                cands = [p for key, p in by_part.items() if key.startswith(_norm(tail)) or _norm(tail).startswith(key)]
                page = cands[0] if len(cands) == 1 else None
            if page is None:
                unmatched += 1
                self.stdout.write(self.style.WARNING(f"  id={video.id} 对不上分P: {video.name}"))
                continue
            try:
                data = get_player_v2(bvid, page["cid"], sessdata)
                native = native_subtitles.fetch_bili(data.get("subtitle"), get_subtitle_body)
                chapters = native_subtitles.chapters_from_view_points(data.get("view_points"))
            except Exception as exc:
                failed += 1
                self.stdout.write(self.style.ERROR(f"  id={video.id} p{page['page']} 抓取失败: {exc}"))
                continue
            if not native:
                nosub += 1
                self.stdout.write(f"  id={video.id} p{page['page']} 没有可用的中文轨")
                continue
            self.stdout.write(
                f"  id={video.id} p{page['page']} {native['kind']} {len(native['segments'])} 段"
                f"{' / ' + str(len(chapters)) + ' 章' if chapters else ''}  {tail[:28]}"
            )
            if not dry:
                _store_native_metadata(video, chapters, native, "Bilibili backfill")
            done += 1

        verb = "将回填" if dry else "已回填"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {done} 条；跳过已有字幕 {skipped}；无中文轨 {nosub}；对不上分P {unmatched}；失败 {failed}"
        ))
        if dry:
            self.stdout.write(self.style.NOTICE("这是 --dry-run，没有写库"))
