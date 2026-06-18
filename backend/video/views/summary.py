import io
import json, time, os, re, threading, logging
import zipfile
from typing import Any, cast
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse, Http404, StreamingHttpResponse
from django.conf import settings
from ..tasks import summary_task_status, summary_task_queue, _get_default_min_coverage

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


def _get_or_create_agent(filename):
    stem = os.path.splitext(filename)[0]
    from ..models import Video
    video = Video.objects.filter(url__contains=stem).first()

    db_dir = os.path.join(settings.MEDIA_ROOT, "vidunder", "db")
    if not os.path.isdir(db_dir):
        return None, video, "No vidunder DB found. Run summary first."
    if not video or not video.srt_path:
        return None, video, "Video has no subtitle. Generate subtitles first."

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
        return None, video, f"No vidunder DB found for {filename}"

    srt_path = os.path.join(settings.MEDIA_ROOT, "saved_srt", video.srt_path)
    if not os.path.exists(srt_path):
        return None, video, f"SRT file not found: {srt_path}"

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
    return agent, video, None


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
        min_coverage = payload.get("min_coverage", _get_default_min_coverage())
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


def _summary_base_name(path_or_name: str) -> str:
    name = os.path.basename(path_or_name)
    for suffix in ("_summary_with_slides.md", "_full_summary.md", "_summary.md"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return os.path.splitext(name)[0]


def _iter_summary_files(output_dir: str):
    for root, _, files in os.walk(output_dir):
        for name in files:
            if name.endswith(".md"):
                yield os.path.join(root, name)


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
        for path in _iter_summary_files(output_dir):
            name = _summary_base_name(path)
            if name.endswith(suffix):
                candidates.append(path)
        candidates.sort(
            key=lambda path: (
                0 if os.path.isdir(os.path.join(os.path.dirname(path), "slides")) else 1,
                0 if "_with_slides" in os.path.basename(path) else 1,
                os.path.relpath(path, output_dir),
            )
        )
        if candidates:
            return candidates[0]

    candidates = []
    for path in _iter_summary_files(output_dir):
        f_stem = _summary_base_name(path)
        if stem.startswith(f_stem) or f_stem.startswith(stem):
            candidates.append(path)
    candidates.sort(
        key=lambda path: (
            0 if os.path.isdir(os.path.join(os.path.dirname(path), "slides")) else 1,
            0 if "_with_slides" in os.path.basename(path) else 1,
            os.path.relpath(path, output_dir),
        )
    )
    summary_file = candidates[0] if candidates else None

    if summary_file and os.path.exists(summary_file):
        return summary_file
    return None


def _normalize_summary_slide_links(content: str, db_name: str, summary_dir: str | None = None) -> str:
    output_root = os.path.join(settings.MEDIA_ROOT, "vidunder", "output")
    per_video_dir = os.path.join(output_root, f"{db_name}_slides")
    shared_dir = os.path.join(output_root, "slides")
    sibling_dir = os.path.join(summary_dir, "slides") if summary_dir else ""

    tmp_slide_dirs = set(re.findall(r'(/tmp/[^)\n"\']+/slides)/[^)\n"\']+', content))
    if tmp_slide_dirs:
        import shutil
        os.makedirs(per_video_dir, exist_ok=True)
        for tmp_dir in tmp_slide_dirs:
            if not os.path.isdir(tmp_dir):
                continue
            for name in os.listdir(tmp_dir):
                src = os.path.join(tmp_dir, name)
                dst = os.path.join(per_video_dir, name)
                if os.path.isfile(src) and not os.path.exists(dst):
                    shutil.copy2(src, dst)

    sibling_prefix = None
    if sibling_dir and os.path.isdir(sibling_dir):
        rel = os.path.relpath(sibling_dir, output_root).replace(os.sep, "/")
        sibling_prefix = f"/media/vidunder/output/{rel}/"
    per_video_prefix = f"/media/vidunder/output/{db_name}_slides/"
    shared_prefix = "/media/vidunder/output/slides/"
    if sibling_prefix:
        slide_prefix = sibling_prefix
    elif os.path.isdir(per_video_dir):
        slide_prefix = per_video_prefix
    else:
        slide_prefix = shared_prefix

    def replace_markdown_relative(match):
        return f"{match.group(1)}{slide_prefix}"

    def replace_markdown_tmp(match):
        return f"{match.group(1)}{slide_prefix}{match.group(2)}"

    def replace_html_relative(match):
        return f"{match.group(1)}{slide_prefix}{match.group(2)}{match.group(3)}"

    def replace_html_tmp(match):
        return f"{match.group(1)}{slide_prefix}{match.group(2)}{match.group(3)}"

    content = re.sub(r'(!\[[^\]]*\]\()slides/', replace_markdown_relative, content)
    content = re.sub(r'(!\[[^\]]*\]\()/tmp/[^)\n]+/slides/([^)\n]+)', replace_markdown_tmp, content)
    content = re.sub(r'(<img\b[^>]*\bsrc=["\'])slides/([^"\']+)(["\'])', replace_html_relative, content)
    content = re.sub(r'(<img\b[^>]*\bsrc=["\'])/tmp/[^"\']+/slides/([^"\']+)(["\'])', replace_html_tmp, content)

    media_output_prefix = os.path.join(output_root, "")
    if media_output_prefix in content:
        media_url_prefix = "/media/vidunder/output/"
        content = content.replace(media_output_prefix, media_url_prefix)

    if not sibling_prefix and not os.path.isdir(per_video_dir) and not os.path.isdir(shared_dir):
        logger.warning("No slide directory found for summary %s", db_name)

    return content


def _find_summary_slide_dir(db_name: str, summary_dir: str | None = None) -> str | None:
    output_root = os.path.join(settings.MEDIA_ROOT, "vidunder", "output")
    candidates = []
    if summary_dir:
        candidates.append(os.path.join(summary_dir, "slides"))
    candidates.extend(
        [
            os.path.join(output_root, f"{db_name}_slides"),
            os.path.join(output_root, "slides"),
        ]
    )
    for path in candidates:
        if path and os.path.isdir(path):
            return path
    return None


def _slide_zip_path(path: str) -> str | None:
    normalized = path.strip().replace("\\", "/")
    if not normalized:
        return None
    for marker in ("/slides/", "_slides/"):
        if marker in normalized:
            name = normalized.split(marker, 1)[1].lstrip("/")
            return f"slides/{name}" if name else None
    if normalized.startswith("./slides/"):
        return normalized[2:]
    if normalized.startswith("slides/"):
        return normalized
    return None


def _rewrite_summary_links_for_zip(content: str) -> str:
    def replace_markdown(match):
        path = match.group(2)
        zip_path = _slide_zip_path(path)
        if not zip_path:
            return match.group(0)
        return f"{match.group(1)}{zip_path}{match.group(3)}"

    def replace_html(match):
        path = match.group(2)
        zip_path = _slide_zip_path(path)
        if not zip_path:
            return match.group(0)
        return f"{match.group(1)}{zip_path}{match.group(3)}"

    content = re.sub(r"(!\[[^\]]*\]\()([^)\n]+)(\))", replace_markdown, content)
    content = re.sub(r"(<img\b[^>]*\bsrc=[\"'])([^\"']+)([\"'])", replace_html, content)
    return content


VALID_SUBTITLE_LANGS = ["en", "zh", "jp", "de"]


@method_decorator(csrf_exempt, name='dispatch')
class SummaryPrerequisitesView(View):
    """GET /api/video-summary/<filename>/prerequisites — check subtitles & raw_lang"""

    def get(self, request, filename):
        stem = os.path.splitext(filename)[0]
        from ..models import Video
        video = Video.objects.filter(url__contains=stem).first()

        if not video:
            return JsonResponse({
                "status": "video_not_found",
                "has_subtitles": False,
                "raw_lang": None,
                "available_langs": [],
            }, status=404)

        # Check which subtitle languages have files on disk
        srt_dir = os.path.join(settings.MEDIA_ROOT, "saved_srt")
        available_langs = []
        for lang in VALID_SUBTITLE_LANGS:
            srt_name = f"{video.id}_{lang}.srt"
            if os.path.exists(os.path.join(srt_dir, srt_name)):
                available_langs.append(lang)

        has_subtitles = len(available_langs) > 0
        raw_lang = video.raw_lang or None

        if not has_subtitles:
            status = "no_subtitles"
        elif not raw_lang:
            status = "raw_lang_not_set"
        else:
            status = "ok"

        return JsonResponse({
            "status": status,
            "video_id": video.id,
            "filename": filename,
            "has_subtitles": has_subtitles,
            "raw_lang": raw_lang,
            "available_langs": available_langs,
        })


@method_decorator(csrf_exempt, name='dispatch')
class VideoSummaryView(View):
    """GET /api/video-summary/<filename> → {summary, slides[], file}"""

    def get(self, request, filename):
        summary_file = _find_summary_file(filename)
        if not summary_file:
            return JsonResponse({"error": f"Summary not found for {filename}"}, status=404)

        with open(summary_file, "r", encoding="utf-8") as f:
            content = f.read()

        db_name = _summary_base_name(summary_file)
        content = _normalize_summary_slide_links(content, db_name, os.path.dirname(summary_file))

        return JsonResponse({
            "summary": content,
            "file": os.path.basename(summary_file),
        })


@method_decorator(csrf_exempt, name='dispatch')
class VideoSummaryExportView(View):
    """GET /api/video-summary/<filename>/export?format=zip."""

    def get(self, request, filename):
        export_format = request.GET.get("format", "zip").lower()
        if export_format != "zip":
            return JsonResponse({"error": "Only zip export is supported"}, status=400)

        summary_file = _find_summary_file(filename)
        if not summary_file:
            return JsonResponse({"error": f"Summary not found for {filename}"}, status=404)

        with open(summary_file, "r", encoding="utf-8") as f:
            content = f.read()

        db_name = _summary_base_name(summary_file)
        summary_dir = os.path.dirname(summary_file)
        slide_dir = _find_summary_slide_dir(db_name, summary_dir)
        content = _rewrite_summary_links_for_zip(content)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("summary.md", content)
            if slide_dir:
                for root, _, files in os.walk(slide_dir):
                    for name in files:
                        src = os.path.join(root, name)
                        if not os.path.isfile(src):
                            continue
                        rel = os.path.relpath(src, slide_dir).replace(os.sep, "/")
                        archive.write(src, f"slides/{rel}")

        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = (
            f'attachment; filename="{db_name}_summary_slides.zip"'
        )
        return response


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

        agent, _, error = _get_or_create_agent(filename)
        if error:
            return JsonResponse({"error": error}, status=404 if "not found" in error.lower() else 400)

        result = agent.ask(question)
        return JsonResponse({"answer": result})


@method_decorator(csrf_exempt, name='dispatch')
class VideoAskStreamView(View):

    def post(self, request, filename):
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON")

        question = payload.get("question", "").strip()
        if not question:
            return JsonResponse({"error": "Missing question"}, status=400)

        agent, _, error = _get_or_create_agent(filename)
        if error:
            return JsonResponse({"error": error}, status=404 if "not found" in error.lower() else 400)

        def event_stream():
            import queue
            event_queue = queue.Queue()

            def on_event(event):
                event_queue.put(event)

            import threading
            def run_ask():
                try:
                    agent.ask(question, on_event=on_event)
                except Exception as exc:
                    event_queue.put({"type": "error", "content": str(exc)})
                finally:
                    event_queue.put(None)

            t = threading.Thread(target=run_ask, daemon=True)
            t.start()

            while True:
                event = event_queue.get()
                if event is None:
                    break
                data = json.dumps(event, ensure_ascii=False)
                yield f"data: {data}\n\n"

        response = StreamingHttpResponse(
            event_stream(),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
