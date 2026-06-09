import json, time, os, re, threading, logging
from typing import Any, cast
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse, Http404
from django.conf import settings
from ..tasks import summary_task_status, summary_task_queue

logger = logging.getLogger("video.summary")

_agent_cache = {}
_agent_cache_order = []
_agent_cache_max = 2
_unload_timer = None


def _unload_oldest_agent():
    if not _agent_cache_order:
        return
    oldest_key = _agent_cache_order.pop(0)
    agent = _agent_cache.pop(oldest_key, None)
    if agent and hasattr(agent, "unload_models"):
        agent.unload_models()
        logger.info("Unloaded oldest agent: %s", oldest_key)


def _unload_all_agents():
    global _unload_timer
    _unload_timer = None
    for key, agent in list(_agent_cache.items()):
        if hasattr(agent, "unload_models"):
            agent.unload_models()
            logger.info("Timer unload agent: %s", key)
    _agent_cache.clear()
    _agent_cache_order.clear()


def _reset_unload_timer():
    global _unload_timer
    if _unload_timer is not None:
        _unload_timer.cancel()
    _unload_timer = threading.Timer(300, _unload_all_agents)
    _unload_timer.daemon = True
    _unload_timer.start()


@method_decorator(csrf_exempt, name='dispatch')
class SummaryAddView(View):
    def post(self, request):
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON")

        video_id = payload.get("video_id")
        if not video_id:
            return JsonResponse({"error": "Missing video_id"}, status=400)

        from ..models import Video
        try:
            video = Video.objects.get(pk=video_id)
        except Video.DoesNotExist:
            return JsonResponse({"error": "Video not found"}, status=404)

        if not video.srt_path:
            return JsonResponse({"error": "Video has no subtitle. Generate subtitles first."}, status=400)

        video_path = os.path.join(settings.MEDIA_ROOT, "saved_video", video.url)
        srt_path = os.path.join(settings.MEDIA_ROOT, "saved_srt", video.srt_path)

        if not os.path.exists(video_path):
            return JsonResponse({"error": f"Video file not found: {video_path}"}, status=404)
        if not os.path.exists(srt_path):
            return JsonResponse({"error": f"SRT file not found: {srt_path}"}, status=404)

        task_id = f"summary_{video_id}_{int(time.time())}"
        min_coverage = payload.get("min_coverage", 0.60)
        language = payload.get("language", "中文")

        summary_task_status[task_id].update({
            "video_id": video_id,
            "video_name": video.name,
            "video_path": video_path,
            "srt_path": srt_path,
            "min_coverage": min_coverage,
            "language": language,
            "status": "Queued",
            "created_at": int(time.time()),
        })

        summary_task_queue.put(task_id)
        return JsonResponse({"task_id": task_id, "status": "Queued"})


class SummaryStatusView(View):
    def get(self, request, task_id=None):
        if task_id:
            task = summary_task_status.get(task_id)
            if not task:
                return JsonResponse({"error": "Task not found"}, status=404)
            return JsonResponse(dict(cast(Any, task)))
        return JsonResponse(dict(summary_task_status), safe=False)


class SummaryDeleteView(View):
    def delete(self, request, task_id):
        if task_id in summary_task_status:
            task = cast(Any, summary_task_status[task_id])
            if task["status"] == "Running":
                return JsonResponse({"error": "Cannot delete running task"}, status=400)
            del summary_task_status[task_id]
            return JsonResponse({"deleted": task_id})
        return JsonResponse({"error": "Task not found"}, status=404)


@method_decorator(csrf_exempt, name='dispatch')
class SummaryRetryView(View):
    def post(self, request, task_id):
        if task_id not in summary_task_status:
            return JsonResponse({"error": "Task not found"}, status=404)
        task = cast(Any, summary_task_status[task_id])
        if task["status"] not in ("Failed", "Completed"):
            return JsonResponse({"error": "Can only retry failed/completed tasks"}, status=400)
        for stage in task["stages"]:
            task["stages"][stage] = "Queued"
            task["stage_progress"][stage] = 0
            task["stage_detail"][stage] = ""
        task["total_progress"] = 0
        task["status"] = "Queued"
        task["error_message"] = ""
        summary_task_queue.put(task_id)
        return JsonResponse({"task_id": task_id, "status": "Queued"})


def _find_summary_file(filename):
    vidunder_dir = os.path.join(settings.MEDIA_ROOT, "vidunder")
    output_dir = os.path.join(vidunder_dir, "output")
    if not os.path.isdir(output_dir):
        return None

    stem = os.path.splitext(filename)[0]

    from ..models import Video
    video = Video.objects.filter(url__contains=stem).first()

    if video:
        for task in summary_task_status.values():
            if task.get("video_id") == video.id and task.get("status") == "Completed":
                result_path = task.get("result_path", "")
                if result_path and os.path.exists(result_path):
                    return result_path

        candidates = []
        suffix = f"_{video.id}"
        for f in os.listdir(output_dir):
            if not f.endswith(".md"):
                continue
            name = f.replace("_summary_with_slides.md", "").replace("_summary.md", "")
            if name.endswith(suffix):
                candidates.append(f)
        candidates.sort(key=lambda f: (0 if "_with_slides" in f else 1, f))
        if candidates:
            path = os.path.join(output_dir, candidates[0])
            if os.path.exists(path):
                return path

    candidates = []
    for f in os.listdir(output_dir):
        if not f.endswith(".md"):
            continue
        f_stem = f.replace("_summary_with_slides.md", "").replace("_summary.md", "")
        if stem.startswith(f_stem) or f_stem.startswith(stem):
            candidates.append(f)
    candidates.sort(key=lambda f: (0 if "_with_slides" in f else 1, f))
    summary_file = os.path.join(output_dir, candidates[0]) if candidates else None

    if summary_file and os.path.exists(summary_file):
        return summary_file
    return None


@method_decorator(csrf_exempt, name='dispatch')
class VideoSummaryView(View):
    """GET /api/video-summary/<filename> → {summary, slides[], file}"""

    def get(self, request, filename):
        summary_file = _find_summary_file(filename)
        if not summary_file:
            return JsonResponse({"error": f"Summary not found for {filename}"}, status=404)

        with open(summary_file, "r", encoding="utf-8") as f:
            content = f.read()

        base = os.path.basename(summary_file)
        db_name = base.replace("_summary_with_slides.md", "").replace("_summary.md", "")
        slide_prefix = f"/media/vidunder/output/{db_name}_slides/"

        content = re.sub(
            r'!\[([^\]]*)\]\((?:/tmp/[^/]+/?)?slides/',
            rf'![\1]({slide_prefix}',
            content,
        )
        content = re.sub(
            r'!\[([^\]]*)\]\(slides/',
            rf'![\1]({slide_prefix}',
            content,
        )

        return JsonResponse({
            "summary": content,
            "file": base,
        })


@method_decorator(csrf_exempt, name='dispatch')
class VideoAskView(View):
    """POST /api/video-ask/<filename>  {question: "..."} → {answer: "..."}"""

    def post(self, request, filename):
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON")

        question = payload.get("question", "").strip()
        if not question:
            return JsonResponse({"error": "Missing question"}, status=400)

        stem = os.path.splitext(filename)[0]

        from ..models import Video
        video = Video.objects.filter(url__contains=stem).first()

        db_dir = os.path.join(settings.MEDIA_ROOT, "vidunder", "db")
        if not os.path.isdir(db_dir):
            return JsonResponse({"error": "No vidunder DB found. Run summary first."}, status=404)

        db_path = None
        if video:
            vid_suffix = f"_{video.id}.json"
            for f in os.listdir(db_dir):
                if f.endswith(vid_suffix):
                    db_path = os.path.join(db_dir, f)
                    break
        if not db_path:
            for f in os.listdir(db_dir):
                if not f.endswith(".json"):
                    continue
                f_stem = os.path.splitext(f)[0]
                if stem.startswith(f_stem) or f_stem.startswith(stem):
                    db_path = os.path.join(db_dir, f)
                    break
        if not db_path or not os.path.exists(db_path):
            return JsonResponse({"error": f"No vidunder DB found for {filename}"}, status=404)
        if not video or not video.srt_path:
            return JsonResponse({"error": "Video has no subtitle. Generate subtitles first."}, status=400)
        srt_path = os.path.join(settings.MEDIA_ROOT, "saved_srt", video.srt_path)
        if not os.path.exists(srt_path):
            return JsonResponse({"error": f"SRT file not found: {srt_path}"}, status=404)

        # ── Get or create cached VideoAgent ──
        agent = _agent_cache.get(db_path)
        if agent is None:
            import sys as _sys
            vid_under_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "vid_under")
            if vid_under_dir not in _sys.path:
                _sys.path.insert(0, vid_under_dir)

            from ..tasks import _inject_vidunder_config
            _inject_vidunder_config()

            from agent import VideoAgent
            from srt_utils import parse_srt

            with open(db_path, encoding="utf-8") as f:
                db = json.load(f)
            srt = parse_srt(srt_path)
            agent = VideoAgent(db, srt)
            _agent_cache[db_path] = agent
            _agent_cache_order.append(db_path)
            logger.info("Created agent for %s, cache size: %d", db_path, len(_agent_cache))
            while len(_agent_cache) > _agent_cache_max:
                _unload_oldest_agent()
        else:
            if db_path in _agent_cache_order:
                _agent_cache_order.remove(db_path)
            _agent_cache_order.append(db_path)

        _reset_unload_timer()
        result = agent.ask(question)
        return JsonResponse({"answer": result})
