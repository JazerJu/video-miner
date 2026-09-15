import yt_dlp
import os
import logging
from typing import Dict, Optional, Any, Callable

from utils.stream_downloader import native_subtitles

logger = logging.getLogger(__name__)



_LOCAL_NODE = "/media/jju/ExtraDisk/VidGo/tools/node-v22.20.0-linux-x64/bin/node"


def _node_runtime():
    """yt-dlp 的 js_runtimes 配置。本地有新版 node 就指过去，否则交给它自己找。"""
    return {"path": _LOCAL_NODE} if os.path.exists(_LOCAL_NODE) else {}


class YouTubeDownloader:
    def __init__(self):
        # Set by download_video: the YouTube subtitle track to use instead of ASR, or None.
        self.native_subtitles = None
        self.base_ydl_opts = {
            "writesubtitles": False,
            "writeautomaticsub": False,
            "ignoreerrors": True,
            "noplaylist": True,
            "quiet": True,
            # yt-dlp 2026.06 把系统的 node-20 标成 unsupported，四个 JS 运行时全
            # unavailable，于是只能退到 android vr player client，媒体 URL 一律
            # 403。这里指向本地解压的 node 22（不装系统包、不改 PATH）。
            "js_runtimes": {"node": _node_runtime()},
            # **别用 mweb**：它只开出一个格式 `18/mp4/360p` 合流、纯音频 0 个。
            # 画质被锁死在 360p，而且请求 bestaudio 时会静默回退成整段视频，
            # 从产物上看不出错（101 分钟的片子拿到 233 MB mp4）。
            # 两个视频上逐 client 实测（走代理 + 登录 cookies）：
            #   client         2wIxPWK6nCs     6Q-ESEmDf4Q
            #   default        84 格式/35 音频  124/78
            #   tv_embedded    84/35           124/78
            #   web_embedded   55/32           Video unavailable
            #   mweb           5/0             5/0
            #   android_vr     5/0             5/0
            #   web_music / web_creator / web / ios / web_safari  取不到
            # 只用 web_embedded 跑 243 个，55 个拿不到纯音频。
            # `default` 当初被判 403，是在没有 node-22 和登录 cookies 的时候测的。
            "extractor_args": {
                "youtube": {
                    "player_client": ["default", "tv_embedded", "web_embedded"]
                }
            },
            # 多语配音轨（意/印尼/德/葡/法）码率和原声接近，纯按码率排会挑中配音，
            # 音频就和字幕对不上了。lang 放第一位才拿得到 original。
            "format_sort": ["lang", "res", "abr"],
        }
        # 自动加载 cookies.txt（如果存在）
        from django.conf import settings as django_settings

        _cookies_path = os.path.join(
            django_settings.MEDIA_ROOT, "cookies", "youtube-cookies.txt"
        )
        if os.path.exists(_cookies_path):
            self.base_ydl_opts["cookiefile"] = _cookies_path

    @staticmethod
    def _format_counts(info_dict: Dict[str, Any]) -> tuple[int, int, int]:
        formats = info_dict.get("formats") or []
        video_count = sum(
            1
            for fmt in formats
            if fmt.get("url") and fmt.get("vcodec") not in (None, "none")
        )
        audio_count = sum(
            1
            for fmt in formats
            if fmt.get("url") and fmt.get("acodec") not in (None, "none")
        )
        return len(formats), video_count, audio_count

    def _get_video_info_attempts(self, ydl_opts: Dict[str, Any]):
        yield "default", ydl_opts
        if "cookiefile" in ydl_opts:
            fallback = ydl_opts.copy()
            fallback.pop("cookiefile", None)
            fallback["extractor_args"] = {
                "youtube": {"player_client": ["default", "android", "ios"]}
            }
            yield "no-cookie-mobile-client", fallback

    def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Extract video information without downloading

        Args:
            url: YouTube video URL

        Returns:
            Dictionary containing video metadata or None if failed
        """
        ydl_opts = self.base_ydl_opts.copy()
        from video.proxy import get_effective_proxy
        from video.views.set_setting import load_all_settings

        settings = load_all_settings()
        use_proxy = (
            settings.get("Media Credentials", {})
            .get("download_use_proxy", "false")
            .lower()
            == "true"
        )
        proxy = get_effective_proxy(use_proxy)
        if proxy:
            ydl_opts["proxy"] = proxy

        last_info = None
        last_error = None
        for attempt_name, attempt_opts in self._get_video_info_attempts(ydl_opts):
            with yt_dlp.YoutubeDL(attempt_opts) as ydl:
                try:
                    info_dict = ydl.extract_info(url, download=False)
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "YouTube info extraction attempt %s failed: %s",
                        attempt_name,
                        e,
                    )
                    continue

                if info_dict is None:
                    logger.warning(
                        "YouTube info extraction attempt %s returned no info",
                        attempt_name,
                    )
                    continue

                total, video_count, audio_count = self._format_counts(info_dict)
                logger.info(
                    "YouTube info extraction attempt %s returned formats=%d video=%d audio=%d cookies=%s",
                    attempt_name,
                    total,
                    video_count,
                    audio_count,
                    bool(attempt_opts.get("cookiefile")),
                )
                last_info = info_dict
                if not video_count or not audio_count:
                    continue

                # Extract key information
                return {
                    "title": info_dict.get("title", ""),
                    "duration": info_dict.get("duration", 0),
                    "uploader": info_dict.get("uploader", ""),
                    "upload_date": info_dict.get("upload_date", ""),
                    "view_count": info_dict.get("view_count", 0),
                    "description": info_dict.get("description", ""),
                    "thumbnail": info_dict.get("thumbnail", ""),
                    "formats": info_dict.get("formats", []),
                    "id": info_dict.get("id", ""),
                    "webpage_url": info_dict.get("webpage_url", ""),
                    "ext": info_dict.get("ext", "mp4"),
                    "chapters": info_dict.get("chapters") or [],
                    "language": info_dict.get("language"),
                }

        if last_info is not None:
            total, video_count, audio_count = self._format_counts(last_info)
            logger.warning(
                "YouTube info extraction found no usable media formats: formats=%d video=%d audio=%d",
                total,
                video_count,
                audio_count,
            )
        elif last_error is not None:
            logger.warning("YouTube info extraction failed: %s", last_error)
        else:
            logger.warning("YouTube info extraction failed")
        return None

    def download_video(
        self,
        url: str,
        output_path: str,
        filename_template: Optional[str] = None,
        merge_audio_video: bool = True,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> Optional[str]:
        """
        Download video from YouTube URL

        Args:
            url: YouTube video URL
            output_path: Directory to save the video
            filename_template: Custom filename template (optional)
            merge_audio_video: Whether to merge separate audio/video streams with ffmpeg

        Returns:
            Path to downloaded file or None if failed
        """
        if not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)

        # Set filename template
        if filename_template is None:
            filename_template = "%(title)s.%(ext)s"

        ydl_opts = self.base_ydl_opts.copy()
        ydl_opts.update(
            {
                "outtmpl": os.path.join(output_path, filename_template),
            }
        )
        if progress_callback:
            def progress_hook(d):
                status = d.get("status")
                if status == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate")
                    downloaded = d.get("downloaded_bytes") or 0
                    if total:
                        progress_callback(min(downloaded / total * 100, 99.0))
                elif status == "finished":
                    progress_callback(100.0)

            ydl_opts["progress_hooks"] = [progress_hook]

        from video.proxy import get_effective_proxy
        from video.views.set_setting import load_all_settings

        settings = load_all_settings()
        use_proxy = (
            settings.get("Media Credentials", {})
            .get("download_use_proxy", "false")
            .lower()
            == "true"
        )
        proxy = get_effective_proxy(use_proxy)
        if proxy:
            ydl_opts["proxy"] = proxy

        # Set format based on preferences
        if merge_audio_video:
            # Try to get separate video and audio, fallback to combined
            ydl_opts["format"] = (
                "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
            )
        else:
            # Get best combined format with reasonable quality
            ydl_opts["format"] = "best[height<=1080]"

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # First get info to determine output filename
                info_dict = ydl.extract_info(url, download=False)

                # Generate the expected output filename
                output_filename = ydl.prepare_filename(info_dict)

                # Download the video
                ydl.process_info(info_dict)

                self.native_subtitles = self._fetch_native_subtitles(ydl, info_dict)
                return output_filename

        except Exception as e:
            print(f"Error downloading video: {e}")
            return None

    @staticmethod
    def _fetch_native_subtitles(ydl, info_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """The video's own subtitles (human-made first, else original-language automatic
        captions) so that ASR can be skipped. A failure here never fails the download."""
        try:
            native = native_subtitles.fetch(ydl, info_dict)
        except Exception as e:
            logger.warning("Native subtitle fetch failed: %s", e)
            return None
        if native:
            logger.info(
                "Native subtitles: %s track %s (%s), %d cues, %d words",
                native["kind"], native["tag"], native["lang"],
                len(native["segments"]), len(native["words"]),
            )
        else:
            logger.info("No usable native subtitles; subtitles will come from ASR")
        return native

    def download_audio_only(
        self, url: str, output_path: str, filename_template: Optional[str] = None
    ) -> Optional[str]:
        """
        Download audio only from YouTube URL

        Args:
            url: YouTube video URL
            output_path: Directory to save the audio
            filename_template: Custom filename template (optional)

        Returns:
            Path to downloaded audio file or None if failed
        """
        if not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)

        if filename_template is None:
            filename_template = "%(title)s.%(ext)s"

        ydl_opts = self.base_ydl_opts.copy()
        ydl_opts.update(
            {
                "format": "bestaudio[ext=m4a]/bestaudio/best",
                "outtmpl": os.path.join(output_path, filename_template),
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }
        )

        from video.proxy import get_effective_proxy
        from video.views.set_setting import load_all_settings

        settings = load_all_settings()
        use_proxy = (
            settings.get("Media Credentials", {})
            .get("download_use_proxy", "false")
            .lower()
            == "true"
        )
        proxy = get_effective_proxy(use_proxy)
        if proxy:
            ydl_opts["proxy"] = proxy

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=False)
                output_filename = ydl.prepare_filename(info_dict)

                # Replace video extension with audio extension
                audio_filename = os.path.splitext(output_filename)[0] + ".mp3"

                ydl.process_info(info_dict)

                return audio_filename

        except Exception as e:
            print(f"Error downloading audio: {e}")
            return None


# Legacy function for backward compatibility
def download_youtube_video(url, output_path):
    downloader = YouTubeDownloader()
    return downloader.download_video(url, output_path)
