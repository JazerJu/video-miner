import os

from django.conf import settings
from django.http import JsonResponse
from django.views import View

from ..models import Video


class VideoLanguageTracksView(View):
    """
    GET /api/video/<video_id>/languages
    获取视频的可用语言轨道列表
    """

    def get(self, request, video_id):
        try:
            video = Video.objects.get(pk=video_id)

            language_names = {
                "en": "English",
                "zh": "中文",
                "jp": "Japanese",
            }

            languages = []

            if video.raw_lang and video.url:
                original_url = f"/media/saved_video/{video.url}"
                full_path = os.path.join(settings.MEDIA_ROOT, "saved_video", video.url)
                if os.path.exists(full_path):
                    languages.append(
                        {
                            "code": video.raw_lang,
                            "name": language_names.get(video.raw_lang, video.raw_lang.upper()),
                            "type": "original",
                            "url": original_url,
                        }
                    )

            base_name = os.path.splitext(video.url)[0] if video.url else str(video.id)
            saved_video_dir = os.path.join(settings.MEDIA_ROOT, "saved_video")

            if os.path.exists(saved_video_dir):
                for filename in os.listdir(saved_video_dir):
                    if not (filename.startswith(base_name) and filename.endswith(".mp4")):
                        continue

                    parts = filename[len(base_name) :].lstrip("_").split(".")
                    if len(parts) < 2:
                        continue

                    lang_code = parts[0]
                    if lang_code in language_names and lang_code != video.raw_lang:
                        languages.append(
                            {
                                "code": lang_code,
                                "name": language_names[lang_code],
                                "type": "tts",
                                "url": f"/media/saved_video/{filename}",
                            }
                        )

            return JsonResponse(
                {
                    "success": True,
                    "data": {
                        "video_id": video_id,
                        "video_name": video.name,
                        "languages": languages,
                    },
                }
            )

        except Video.DoesNotExist:
            return JsonResponse({"success": False, "error": "Video not found"}, status=404)
        except Exception as e:
            print(f"[Language Tracks API] Error: {e}")
            return JsonResponse({"success": False, "error": str(e)}, status=500)
