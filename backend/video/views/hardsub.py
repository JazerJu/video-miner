# -*- coding: utf-8 -*-
"""硬字幕提取任务的接口。字幕区域由用户在前端框选后传进来。"""
import json
import os
import subprocess

from django.conf import settings
from django.http import (Http404, HttpResponse, HttpResponseBadRequest,
                         HttpResponseNotAllowed, JsonResponse)
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from video.models import Video
from video.tasks import hardsub_task_status, subtitle_task_queue


def _clamp01(value, default):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, v))


@method_decorator(csrf_exempt, name="dispatch")
class HardsubAddView(View):
    """POST /api/tasks/hardsub/add  {video_id, region:{x,y,w,h}, fps, keep_en}"""

    def post(self, request):
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON")

        video_id = payload.get("video_id")
        if not video_id:
            return JsonResponse({"error": "Missing video_id"}, status=400)
        try:
            video = Video.objects.get(pk=int(video_id))
        except (Video.DoesNotExist, ValueError, TypeError):
            return JsonResponse({"error": "video not found"}, status=404)

        region = payload.get("region") or {}
        x = _clamp01(region.get("x"), 0.0)
        y = _clamp01(region.get("y"), 0.84)
        w = _clamp01(region.get("w"), 1.0)
        h = _clamp01(region.get("h"), 0.13)
        if w <= 0 or h <= 0 or x + w > 1.0001 or y + h > 1.0001:
            return JsonResponse({"error": "region out of range"}, status=400)

        fps = payload.get("fps", 4)
        fps = 8 if str(fps) == "8" else 4

        existing = hardsub_task_status.get(int(video_id))
        if existing and existing["stages"]["extract"] == "Running":
            return JsonResponse({"error": "task already running"}, status=409)

        hardsub_task_status.pop(int(video_id), None)
        task = hardsub_task_status[int(video_id)]
        task["filename"] = video.name
        task["video_id"] = int(video_id)
        task["region"] = {"x": x, "y": y, "w": w, "h": h}
        task["fps"] = fps
        task["keep_en"] = bool(payload.get("keep_en"))
        subtitle_task_queue.put(f"hs_{int(video_id)}")
        return JsonResponse({"success": True})


class HardsubStatusView(View):
    """GET /api/tasks/hardsub/status"""

    def get(self, request):
        return JsonResponse({str(k): v for k, v in hardsub_task_status.items()})


@method_decorator(csrf_exempt, name="dispatch")
class HardsubTaskActionView(View):
    """POST /api/tasks/hardsub/<video_id>/<action>  action = delete | retry"""

    def dispatch(self, request, *args, **kwargs):
        self.action = kwargs.pop("action", None)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, video_id):
        task = hardsub_task_status.get(video_id)
        if task is None:
            return JsonResponse({"error": "task not found"}, status=404)
        if self.action == "delete":
            if task["stages"]["extract"] == "Running":
                return JsonResponse({"error": "task is running"}, status=409)
            hardsub_task_status.pop(video_id, None)
            return JsonResponse({"success": True})
        if self.action == "retry":
            if task["stages"]["extract"] == "Running":
                return JsonResponse({"error": "task is running"}, status=409)
            for stage in task["stages"]:
                task["stages"][stage] = "Queued"
                task["stage_progress"][stage] = 0
                task["stage_detail"][stage] = ""
            task["total_progress"] = 0
            task["error"] = ""
            subtitle_task_queue.put(f"hs_{video_id}")
            return JsonResponse({"success": True})
        return HttpResponseNotAllowed(["POST"])


class VideoFrameView(View):
    """GET /api/videos/<video_id>/frame?t=12.5&w=960 -> 一张 JPEG

    Chrome 在 Linux 上解不了 HEVC：不报错、readyState 照样到 4，就是不出帧
    （实测 canPlayType('video/mp4; codecs="hvc1"') 返回 no）。
    库里约六分之一的视频是 HEVC，那些视频的框选对话框只会显示一块黑区。
    这个接口让前端退回到服务器取帧。单帧提取实测 0.32 秒，够交互用。
    """

    def get(self, request, video_id):
        try:
            video = Video.objects.get(pk=video_id)
        except Video.DoesNotExist:
            raise Http404("video not found")

        path = os.path.join(settings.MEDIA_ROOT, "saved_video", video.url or "")
        if not video.url or not os.path.exists(path):
            raise Http404("media file not found")

        try:
            seconds = max(0.0, float(request.GET.get("t", 0)))
        except (TypeError, ValueError):
            seconds = 0.0
        try:
            width = int(request.GET.get("w", 960))
        except (TypeError, ValueError):
            width = 960
        width = max(160, min(width, 1920))

        # -ss 放在 -i 前面是关键帧快速定位，3 小时的片子也是 0.3 秒量级
        cmd = [
            "ffmpeg", "-v", "error", "-ss", f"{seconds:.3f}", "-i", path,
            "-frames:v", "1", "-vf", f"scale={width}:-2",
            "-f", "image2", "-c:v", "mjpeg", "-q:v", "4", "pipe:1",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            return JsonResponse({"error": "frame extraction timed out"}, status=504)
        if proc.returncode != 0 or not proc.stdout:
            return JsonResponse({"error": "frame extraction failed"}, status=500)

        resp = HttpResponse(proc.stdout, content_type="image/jpeg")
        resp["Cache-Control"] = "public, max-age=300"
        return resp
