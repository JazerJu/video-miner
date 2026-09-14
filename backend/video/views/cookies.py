import os
from datetime import datetime, timezone

from django.conf import settings
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt


COOKIES_DIR = os.path.join(settings.MEDIA_ROOT, "cookies")


@method_decorator(csrf_exempt, name="dispatch")
class YoutubeCookiesUploadView(View):
    """POST /api/cookies/youtube/upload — 上传 cookies.txt，覆盖旧文件"""

    http_method_names = ["post"]

    def post(self, request):
        if "cookies_file" not in request.FILES:
            return JsonResponse({"success": False, "error": "未提供文件"}, status=400)

        uploaded = request.FILES["cookies_file"]
        file_ext = os.path.splitext(uploaded.name)[1].lower()
        if file_ext not in (".txt", ""):
            return JsonResponse(
                {"success": False, "error": "仅支持 .txt 文件"}, status=400
            )

        if uploaded.size > 1 * 1024 * 1024:
            return JsonResponse(
                {"success": False, "error": "文件大小不能超过 1MB"}, status=400
            )

        os.makedirs(COOKIES_DIR, exist_ok=True)
        save_path = os.path.join(COOKIES_DIR, "youtube-cookies.txt")

        with open(save_path, "wb") as f:
            for chunk in uploaded.chunks():
                f.write(chunk)

        mtime = os.path.getmtime(save_path)
        last_modified = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

        return JsonResponse(
            {
                "success": True,
                "filename": "youtube-cookies.txt",
                "last_modified": last_modified,
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class YoutubeCookiesStatusView(View):
    """GET /api/cookies/youtube/status — 查询 cookies.txt 是否存在及修改时间"""

    http_method_names = ["get"]

    def get(self, request):
        save_path = os.path.join(COOKIES_DIR, "youtube-cookies.txt")
        if not os.path.exists(save_path):
            return JsonResponse({"success": True, "exists": False})

        mtime = os.path.getmtime(save_path)
        last_modified = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        file_size = os.path.getsize(save_path)

        return JsonResponse(
            {
                "success": True,
                "exists": True,
                "filename": "youtube-cookies.txt",
                "last_modified": last_modified,
                "file_size": file_size,
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class YoutubeCookiesClearView(View):
    """POST /api/cookies/youtube/clear — 删除已保存的 cookies.txt，之后下载不带 cookies。

    YouTube 对带和不带 cookies 的请求用的反爬策略不同，带着过期或被风控的 cookies 反而下不动，
    所以要能切回无 cookies 状态。下载器只在文件存在时才传 cookiefile，删掉文件即可。
    """

    http_method_names = ["post"]

    def post(self, request):
        save_path = os.path.join(COOKIES_DIR, "youtube-cookies.txt")
        removed = os.path.exists(save_path)
        if removed:
            os.remove(save_path)
        return JsonResponse({"success": True, "removed": removed})
