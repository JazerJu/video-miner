import json
import time
import uuid
from contextlib import contextmanager
from urllib.parse import urlencode, urlparse

import requests
from django.http import JsonResponse, StreamingHttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from utils.stream_downloader import bili_download
from utils.stream_downloader.bili_download import (
    extract_av_bv_p,
    get_video_info,
    get_video_url,
    parse_video_url,
)
from utils.stream_downloader.youtube_download import YouTubeDownloader
from video.proxy import get_effective_proxy
from video.stream_transcriber import (
    cancel_transcription,
    start_transcription,
    _transcription_status,
    _transcription_events,
)
from video.views.set_setting import load_all_settings

DEFAULT_BROWSER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def _parse_json_body(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _is_enabled(value):
    return str(value).strip().lower() == "true"


def _get_download_proxy():
    settings_data = load_all_settings()
    media_settings = settings_data.get("Media Credentials", {})
    return get_effective_proxy(
        _is_enabled(media_settings.get("download_use_proxy", "false"))
    )


def _build_requests_proxies(proxy_url):
    if proxy_url:
        return {"http": proxy_url, "https": proxy_url}
    return None


def _build_relay_url(request, target_url, headers=None):
    params = {"url": target_url}
    headers = headers or {}
    referer = headers.get("Referer") or headers.get("referer")
    user_agent = headers.get("User-Agent") or headers.get("user-agent")
    if referer:
        params["referer"] = referer
    if _should_use_browser_user_agent(target_url, user_agent):
        params["user_agent"] = DEFAULT_BROWSER_USER_AGENT
    elif user_agent:
        params["user_agent"] = user_agent
    return request.build_absolute_uri(
        f"/api/stream_transcription/proxy?{urlencode(params)}"
    )


def _should_use_browser_user_agent(target_url, current_user_agent=""):
    host = (urlparse(target_url).hostname or "").lower()
    if not (
        host.endswith("bilivideo.com")
        or host.endswith("bilibili.com")
        or host.endswith("hdslb.com")
    ):
        return False
    normalized = (current_user_agent or "").lower()
    return (
        not normalized
        or normalized.startswith("lavf/")
        or normalized.startswith("python-requests/")
        or normalized.startswith("ffmpeg/")
    )


def _detect_platform(url):
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host in {"youtube.com", "m.youtube.com", "youtu.be"}:
        return "youtube"
    if host.endswith("bilibili.com") or host == "b23.tv":
        return "bilibili"
    return None


def _select_youtube_video_format(formats):
    combined_candidates = []
    video_only_candidates = []
    for fmt in formats or []:
        if not fmt.get("url"):
            continue
        if fmt.get("vcodec") in (None, "none"):
            continue
        height = fmt.get("height") or 0
        if height > 1080:
            continue
        vcodec = (fmt.get("vcodec") or "").lower()
        ext = (fmt.get("ext") or "").lower()
        protocol = (fmt.get("protocol") or "").lower()
        if protocol.startswith("m3u8"):
            continue
        has_audio = fmt.get("acodec") not in (None, "none")
        candidate = (
            (
                1 if "avc1" in vcodec or "h264" in vcodec else 0,
                1 if ext == "mp4" else 0,
                1 if protocol == "https" else 0,
                height,
                fmt.get("tbr") or 0,
                str(fmt.get("format_id") or ""),
                fmt,
            )
        )
        if has_audio:
            combined_candidates.append(candidate)
        else:
            video_only_candidates.append(candidate)
    if combined_candidates:
        return max(combined_candidates)[-1]
    if video_only_candidates:
        return max(video_only_candidates)[-1]
    return None


def _select_youtube_audio_format(formats):
    candidates = []
    for fmt in formats or []:
        if not fmt.get("url"):
            continue
        if fmt.get("acodec") in (None, "none"):
            continue
        if fmt.get("vcodec") not in (None, "none"):
            continue
        format_note = (fmt.get("format_note") or "").lower()
        language = str(fmt.get("language") or "").lower()
        audio_track = str(fmt.get("audio_track") or "").lower()
        url = str(fmt.get("url") or "")
        url_lower = url.lower()
        source_preference = fmt.get("source_preference")
        is_original = "original" in format_note
        is_default = "default" in format_note
        is_drc = "drc" in format_note
        is_dubbed = "dubbed" in format_note or "dubbed-auto" in url_lower
        if is_dubbed:
            continue
        if any(tag in language for tag in ["dub", "descriptive", "commentary"]):
            continue
        if any(tag in audio_track for tag in ["dub", "descriptive", "commentary"]):
            continue
        ext = (fmt.get("ext") or "").lower()
        acodec = (fmt.get("acodec") or "").lower()
        protocol = (fmt.get("protocol") or "").lower()
        has_manifest = 1 if fmt.get("manifest_url") else 0
        candidates.append(
            (
                1 if is_original else 0,
                1 if is_default else 0,
                0 if is_drc else 1,
                1 if ext == "m4a" else 0,
                1 if acodec.startswith("mp4a") else 0,
                1 if protocol == "https" else 0,
                -has_manifest,
                source_preference
                if isinstance(source_preference, (int, float))
                else -9999,
                fmt.get("filesize") or fmt.get("filesize_approx") or 0,
                fmt.get("abr") or 0,
                fmt.get("asr") or 0,
                str(fmt.get("format_id") or ""),
                fmt,
            )
        )
    if not candidates:
        return None
    return max(candidates)[-1]


def _bilibili_headers(referer=None, sessdata=""):
    headers = {
        "Referer": referer or "https://www.bilibili.com",
        "User-Agent": DEFAULT_BROWSER_USER_AGENT,
    }
    if sessdata:
        headers["Cookie"] = f"SESSDATA={sessdata}"
    return headers


@contextmanager
def _patched_bilibili_proxies(proxy_url):
    original = bili_download.get_proxies
    proxy_config = _build_requests_proxies(proxy_url)
    bili_download.get_proxies = lambda: proxy_config
    try:
        yield
    finally:
        bili_download.get_proxies = original


def _fetch_bilibili_view_data(bvid=None, avid=None, proxy_url=None, sessdata=""):
    if bvid:
        api_url = f"https://api.bilibili.com/x/web-interface/wbi/view?bvid={bvid}"
    elif avid:
        api_url = f"https://api.bilibili.com/x/web-interface/wbi/view?aid={avid}"
    else:
        raise ValueError("Either bvid or avid must be provided.")
    response = requests.get(
        api_url,
        headers=_bilibili_headers(sessdata=sessdata),
        proxies=_build_requests_proxies(proxy_url),
        timeout=(10, 30),
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") or {}
    if not data:
        raise ValueError("Bilibili video data is empty")
    return data


def _pick_bilibili_cid(view_data, p_value):
    pages = view_data.get("pages") or []
    if p_value:
        try:
            index = max(int(p_value) - 1, 0)
            if index < len(pages):
                return pages[index].get("cid")
        except (TypeError, ValueError):
            pass
    if view_data.get("cid"):
        return view_data.get("cid")
    if pages:
        return pages[0].get("cid")
    return None


def _select_bilibili_dash_items(playurl_json):
    dash = (playurl_json.get("data") or {}).get("dash") or {}
    videos = dash.get("video") or []
    audios = dash.get("audio") or []
    video_item = next((item for item in videos if item.get("id") == 80), None)
    if not video_item:
        video_item = next((item for item in videos if item.get("id") == 64), None)
    if not video_item and videos:
        video_item = videos[0]
    audio_item = next((item for item in audios if item.get("id") == 30280), None)
    if not audio_item and audios:
        audio_item = audios[0]
    return video_item, audio_item


def _resolve_youtube(url):
    downloader = YouTubeDownloader()
    info = downloader.get_video_info(url)
    if not info:
        raise ValueError("Failed to resolve YouTube stream info")
    video_format = _select_youtube_video_format(info.get("formats", []))
    audio_format = _select_youtube_audio_format(info.get("formats", []))
    if not video_format or not audio_format:
        raise ValueError("Unable to find suitable YouTube video/audio streams")
    return {
        "success": True,
        "platform": "youtube",
        "title": info.get("title", ""),
        "duration": info.get("duration") or 0,
        "thumbnail": info.get("thumbnail", ""),
        "video": {
            "url": video_format.get("url", ""),
            "format_id": str(video_format.get("format_id", "")),
            "height": video_format.get("height"),
            "ext": video_format.get("ext", ""),
            "protocol": video_format.get("protocol", ""),
            "has_audio": video_format.get("acodec") not in (None, "none"),
            "requires_relay": True,
            "headers": {},
        },
        "audio": {
            "url": audio_format.get("url", ""),
            "format_id": str(audio_format.get("format_id", "")),
            "ext": audio_format.get("ext", ""),
            "protocol": audio_format.get("protocol", ""),
            "language": audio_format.get("language", ""),
            "requires_relay": True,
            "headers": {},
        },
    }


def _resolve_bilibili(url):
    settings_data = load_all_settings()
    media_settings = settings_data.get("Media Credentials", {})
    sessdata = media_settings.get("bilibili_sessdata", "").strip()
    proxy_url = _get_download_proxy()
    bvid, avid, p_value = extract_av_bv_p(url)
    with _patched_bilibili_proxies(proxy_url):
        info = get_video_info(bvid=bvid, avid=avid)
        view_data = _fetch_bilibili_view_data(
            bvid=info.get("bvid") or bvid,
            avid=avid,
            proxy_url=proxy_url,
            sessdata=sessdata,
        )
        cid = _pick_bilibili_cid(view_data, p_value)
        if not cid:
            raise ValueError("Unable to resolve Bilibili cid")
        playurl_json = get_video_url(info["bvid"], cid, sessdata)
        urls = parse_video_url(playurl_json)
    video_item, audio_item = _select_bilibili_dash_items(playurl_json)
    video_url = urls.get("vidBaseUrl") or urls.get("vidBackUrl")
    audio_url = urls.get("audBaseUrl") or urls.get("audBackUrl")
    if not video_url or not audio_url:
        raise ValueError("Unable to resolve Bilibili dash streams")
    headers = _bilibili_headers(referer="https://www.bilibili.com")
    return {
        "success": True,
        "platform": "bilibili",
        "title": info.get("title", ""),
        "duration": info.get("duration") or 0,
        "thumbnail": info.get("pic_url", ""),
        "video": {
            "url": video_url,
            "format_id": str((video_item or {}).get("id", "")),
            "height": (video_item or {}).get("height"),
            "has_audio": False,
            "requires_relay": True,
            "headers": headers,
        },
        "audio": {
            "url": audio_url,
            "format_id": str((audio_item or {}).get("id", "")),
            "requires_relay": True,
            "headers": headers,
        },
    }


@method_decorator(csrf_exempt, name="dispatch")
class ResolveView(View):
    def post(self, request):
        data = _parse_json_body(request)
        if data is None:
            return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
        url = (data.get("url") or "").strip()
        if not url:
            return JsonResponse(
                {"success": False, "error": 'Missing "url" field'}, status=400
            )
        platform = _detect_platform(url)
        if not platform:
            return JsonResponse(
                {"success": False, "error": "Unsupported URL platform"}, status=400
            )
        try:
            result = (
                _resolve_youtube(url)
                if platform == "youtube"
                else _resolve_bilibili(url)
            )
            return JsonResponse(result)
        except Exception as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=502)


class StreamProxyView(View):
    _PASSTHROUGH_RESPONSE_HEADERS = [
        "Content-Type",
        "Content-Length",
        "Content-Range",
        "Accept-Ranges",
        "Cache-Control",
        "Content-Disposition",
    ]

    def _build_upstream_headers(self, request):
        headers = {}
        target_url = (request.GET.get("url") or "").strip()
        referer = (request.GET.get("referer") or "").strip()
        if referer:
            headers["Referer"] = referer
        user_agent = (request.GET.get("user_agent") or "").strip()
        if user_agent:
            headers["User-Agent"] = user_agent
        else:
            forwarded_user_agent = request.headers.get("User-Agent")
            if _should_use_browser_user_agent(target_url, forwarded_user_agent):
                headers["User-Agent"] = DEFAULT_BROWSER_USER_AGENT
            elif forwarded_user_agent:
                headers["User-Agent"] = forwarded_user_agent
        range_header = request.headers.get("Range")
        if range_header:
            headers["Range"] = range_header
        return headers

    def _add_proxy_headers(self, response):
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Headers"] = "Range, Content-Type"
        response["Access-Control-Expose-Headers"] = ", ".join(
            self._PASSTHROUGH_RESPONSE_HEADERS
        )
        return response

    def _proxy(self, request, method):
        target_url = (request.GET.get("url") or "").strip()
        if not target_url:
            return JsonResponse(
                {"success": False, "error": 'Missing "url" query parameter'},
                status=400,
            )
        proxy_url = _get_download_proxy()
        try:
            upstream = requests.request(
                method,
                target_url,
                headers=self._build_upstream_headers(request),
                stream=True,
                proxies=_build_requests_proxies(proxy_url),
                timeout=(10, 60),
            )
        except requests.RequestException as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=502)

        if method == "HEAD":
            try:
                response = StreamingHttpResponse(status=upstream.status_code)
                for header_name in self._PASSTHROUGH_RESPONSE_HEADERS:
                    header_value = upstream.headers.get(header_name)
                    if header_value:
                        response[header_name] = header_value
                return self._add_proxy_headers(response)
            finally:
                upstream.close()

        def stream_content():
            try:
                for chunk in upstream.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk
            finally:
                upstream.close()

        response = StreamingHttpResponse(
            stream_content(),
            status=upstream.status_code,
            content_type=upstream.headers.get(
                "Content-Type", "application/octet-stream"
            ),
        )
        for header_name in self._PASSTHROUGH_RESPONSE_HEADERS:
            header_value = upstream.headers.get(header_name)
            if header_value:
                response[header_name] = header_value
        return self._add_proxy_headers(response)

    def get(self, request):
        return self._proxy(request, "GET")

    def head(self, request):
        return self._proxy(request, "HEAD")


@method_decorator(csrf_exempt, name="dispatch")
class CancelTranscriptionView(View):
    def post(self, request):
        data = _parse_json_body(request)
        if data is None:
            return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
        task_id = str(data.get("task_id") or "").strip()
        if not task_id:
            return JsonResponse(
                {"success": False, "error": 'Missing "task_id" field'}, status=400
            )
        cancelled = cancel_transcription(task_id)
        if not cancelled:
            return JsonResponse(
                {
                    "success": False,
                    "status": "not_found",
                    "task_id": task_id,
                    "error": "Task not found or already finished",
                },
                status=404,
            )
        return JsonResponse(
            {"success": True, "status": "cancelled", "task_id": task_id}
        )


@method_decorator(csrf_exempt, name="dispatch")
class StartView(View):
    def post(self, request):
        data = _parse_json_body(request)
        if data is None:
            return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
        audio_url = (data.get("audio_url") or "").strip()
        if not audio_url:
            return JsonResponse(
                {"success": False, "error": 'Missing "audio_url" field'}, status=400
            )
        audio_headers = data.get("audio_headers") or {}
        requires_relay = _is_enabled(data.get("requires_relay", False))
        if requires_relay and not audio_headers:
            audio_url = _build_relay_url(request, audio_url, audio_headers)
            audio_headers = {}
            proxy_url = None
        else:
            proxy_url = _get_download_proxy()
        task_id = str(uuid.uuid4())
        start_transcription(task_id, audio_url, proxy_url, audio_headers)
        return JsonResponse({"success": True, "task_id": task_id})


class TranscriptionSSEView(View):
    def get(self, request, task_id):
        event_queue = _transcription_events.get(task_id)
        if event_queue is None:
            return JsonResponse(
                {"success": False, "error": "Unknown task_id"}, status=404
            )

        def event_stream():
            while True:
                status = _transcription_status.get(task_id)
                if status is None:
                    break
                try:
                    event_type, payload = event_queue.get(timeout=1.0)
                except Exception:
                    if status.get("status") in ("Completed", "Failed", "Cancelled"):
                        break
                    continue
                yield f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if event_type in ("complete", "end", "error"):
                    break

        response = StreamingHttpResponse(
            event_stream(), content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
