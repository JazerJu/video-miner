# -*- coding: utf-8 -*-
"""find_clips 的片段索引接口：建索引、查状态、检索。

建索引排进 summary_task_queue，和视频总结共用那 1 个 worker，不会和总结同时占 GPU。
"""
import glob
import json
import os
import sys
import time

from django.conf import settings
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from ..tasks import clip_index_task_status, summary_task_queue

INDEX_DIR = os.path.join(settings.MEDIA_ROOT, "vidunder", "index")
_VID_UNDER = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                          "vid_under")
_PUBLIC_TASK_KEYS = ("task_id", "video_id", "video_name", "status", "progress", "detail", "force_index",
                     "index_quality", "n_segments", "build_seconds", "error_message",
                     "created_at", "started_at", "finished_at")


def _clip_index():
    if _VID_UNDER not in sys.path:
        sys.path.insert(0, _VID_UNDER)
    import clip_index
    return clip_index


def _get_video(video_id):
    from ..models import Video
    try:
        return Video.objects.get(pk=int(video_id))
    except (Video.DoesNotExist, TypeError, ValueError):
        return None


def _video_sources(video):
    """视频文件、字幕、最近一次视频理解产出的屏幕文字。后两者可能没有。"""
    video_path = os.path.join(settings.MEDIA_ROOT, "saved_video", video.url)
    srt_path = os.path.join(settings.MEDIA_ROOT, "saved_srt", video.srt_path) if video.srt_path else None
    structure_path = None
    hits = sorted(glob.glob(os.path.join(settings.MEDIA_ROOT, "vidunder", "db", f"*_{video.id}.json")))
    if hits:
        try:
            with open(hits[-1], encoding="utf-8") as fh:
                candidate = json.load(fh).get("structure_path")
            if candidate and os.path.exists(candidate):
                structure_path = candidate
        except (OSError, ValueError):
            pass
    return video_path, srt_path, structure_path


def _active_task(video_id):
    for task_id, task in clip_index_task_status.items():
        if task.get("video_id") == video_id and task.get("status") in ("Queued", "Running"):
            return task_id, task
    return None, None


def _public(task):
    return {k: task[k] for k in _PUBLIC_TASK_KEYS if k in task}


def _payload(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


@method_decorator(csrf_exempt, name="dispatch")
class ClipIndexAddView(View):
    def post(self, request):
        payload = _payload(request)
        if payload is None:
            return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)
        video = _get_video(payload.get("video_id"))
        if video is None:
            return JsonResponse({"ok": False, "error": "video_not_found"}, status=404)
        force_index = bool(payload.get("force_index", False))
        video_path, srt_path, structure_path = _video_sources(video)
        if not os.path.exists(video_path):
            return JsonResponse({"ok": False, "error": "video_file_missing",
                                 "message": f"Video file not found: {video_path}"}, status=404)
        ci = _clip_index()
        # 提交时就检查字幕，Agent 立刻拿到提示，不用等排队跑到它才失败
        if not ci.load_subtitles(srt_path) and not force_index:
            return JsonResponse(ci.no_subtitles_payload(video.id), status=400)
        task_id, task = _active_task(video.id)
        if task_id:
            return JsonResponse({"ok": True, **_public(task),
                                 "note": "An index task for this video is already queued or running."})
        task_id = f"clipindex_{video.id}_{int(time.time())}"
        clip_index_task_status[task_id] = {
            "task_id": task_id, "video_id": video.id, "video_name": video.name,
            "video_path": video_path, "srt_path": srt_path, "structure_path": structure_path,
            "index_dir": INDEX_DIR, "force_index": force_index,
            "status": "Queued", "progress": 0, "detail": "", "created_at": int(time.time()),
        }
        summary_task_queue.put(task_id)
        return JsonResponse({"ok": True, "task_id": task_id, "status": "Queued",
                             "has_subtitles": bool(ci.load_subtitles(srt_path)),
                             "has_screen_text": structure_path is not None})


@method_decorator(csrf_exempt, name="dispatch")
class ClipIndexStatusView(View):
    def get(self, request, task_id=None):
        if task_id:
            task = clip_index_task_status.get(task_id)
            if not task:
                return JsonResponse({"ok": False, "error": "task_not_found"}, status=404)
            return JsonResponse({"ok": True, **_public(task)})
        video_id = request.GET.get("video_id")
        if not video_id:
            return JsonResponse({"ok": True, "tasks": [_public(t) for t in clip_index_task_status.values()]})
        video = _get_video(video_id)
        if video is None:
            return JsonResponse({"ok": False, "error": "video_not_found"}, status=404)
        video_path, srt_path, structure_path = _video_sources(video)
        status = _clip_index().index_status(video.id, INDEX_DIR, video_path, srt_path, structure_path)
        _, task = _active_task(video.id)
        if task:
            status["task"] = _public(task)
        if status["state"] == "stale":
            status["hint"] = ("Subtitles, screen text or the video changed since the index was built "
                              f"({', '.join(status['stale_sources'])}); resubmit with submit_clip_index_task.")
        return JsonResponse({"ok": True, "video_id": video.id, **status})


@method_decorator(csrf_exempt, name="dispatch")
class ClipIndexSearchView(View):
    def post(self, request):
        payload = _payload(request)
        if payload is None:
            return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)
        video = _get_video(payload.get("video_id"))
        if video is None:
            return JsonResponse({"ok": False, "error": "video_not_found"}, status=404)
        query = str(payload.get("query") or "").strip()
        if not query:
            return JsonResponse({"ok": False, "error": "empty_query"}, status=400)
        top_k = max(1, min(int(payload.get("top_k") or 5), 20))

        video_path, srt_path, structure_path = _video_sources(video)
        ci = _clip_index()
        status = ci.index_status(video.id, INDEX_DIR, video_path, srt_path, structure_path)
        if status["state"] == "missing":
            _, task = _active_task(video.id)
            if task:
                return JsonResponse({
                    "ok": False, "error": "index_building",
                    "message": f"The clip index for video {video.id} is {task['status'].lower()} "
                               f"({task.get('progress', 0)}%).",
                    "hints": [f"Poll get_clip_index_status(video_id={video.id}) until it completes."],
                }, status=409)
            return JsonResponse({
                "ok": False, "error": "no_index",
                "message": f"Video {video.id} has no clip index yet.",
                "hints": [f"Call submit_clip_index_task(video_id={video.id}), then poll "
                          "get_clip_index_status until it completes."],
            }, status=404)
        try:
            result = ci.search_clip_index(video.id, INDEX_DIR, query, top_k=top_k)
        except RuntimeError as exc:
            return JsonResponse({"ok": False, "error": "encoder_unavailable", "message": str(exc)}, status=503)
        result["video_id"] = video.id
        result["index_state"] = status["state"]
        if status["state"] == "stale":
            result["hint"] = ("The index is older than the current subtitles/screen text/video "
                              f"({', '.join(status['stale_sources'])}); results may be off. "
                              "Resubmit with submit_clip_index_task.")
        if result.get("index_quality") == "no_subtitles":
            result["note"] = ("This index was built without subtitles: matches for what is shown on screen are "
                              "reliable, matches for what the speaker says are not.")
        return JsonResponse(result)
