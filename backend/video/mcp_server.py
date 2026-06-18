"""VidGo MCP tools exposed through the optional ASGI MCP process."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from asgiref.sync import sync_to_async
from django.db import close_old_connections
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.server import TransportSecuritySettings

from video.models import Video
from video.views.videos import VideoSearchView


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _run_with_db_cleanup(func, *args, **kwargs):
    close_old_connections()
    try:
        return func(*args, **kwargs)
    finally:
        close_old_connections()


async def _run_sync(func, *args, **kwargs):
    return await sync_to_async(_run_with_db_cleanup, thread_sensitive=True)(
        func,
        *args,
        **kwargs,
    )


async def _run_blocking(func, *args, **kwargs):
    return await sync_to_async(func, thread_sensitive=False)(*args, **kwargs)


def _csv_env(name: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


def _host_patterns_from_url(url: str) -> list[str]:
    if not url:
        return []
    parsed = urlparse(url if "://" in url else f"http://{url}")
    if not parsed.hostname:
        return []
    return [f"{parsed.hostname}:*"]


def _origin_patterns_from_url(url: str) -> list[str]:
    if not url:
        return []
    parsed = urlparse(url if "://" in url else f"http://{url}")
    if not parsed.hostname:
        return []
    return [f"{parsed.scheme or 'http'}://{parsed.hostname}:*"]


def _transport_security_settings() -> TransportSecuritySettings:
    enabled = os.environ.get("VIDGO_MCP_DNS_REBINDING_PROTECTION", "1").lower() not in {
        "0",
        "false",
        "no",
    }
    allowed_hosts = [
        "localhost:*",
        "127.0.0.1:*",
        "[::1]:*",
        *_host_patterns_from_url(os.environ.get("VIDGO_URL", "")),
        *_host_patterns_from_url(os.environ.get("VIDGO_MCP_PUBLIC_URL", "")),
        *_csv_env("VIDGO_MCP_ALLOWED_HOSTS"),
    ]
    allowed_origins = [
        "http://localhost:*",
        "http://127.0.0.1:*",
        "http://[::1]:*",
        *_origin_patterns_from_url(os.environ.get("VIDGO_URL", "")),
        *_origin_patterns_from_url(os.environ.get("VIDGO_MCP_PUBLIC_URL", "")),
        *_csv_env("VIDGO_MCP_ALLOWED_ORIGINS"),
    ]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=enabled,
        allowed_hosts=list(dict.fromkeys(allowed_hosts)),
        allowed_origins=list(dict.fromkeys(allowed_origins)),
    )


def _video_payload(video: Video, include_filename: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": video.id,
        "title": video.name,
        "duration": video.video_length or "",
        "duration_seconds": video.video_length_seconds,
        "raw_lang": video.raw_lang or "",
        "category": video.category.name if video.category else None,
        "tags": list(video.tags.values_list("name", flat=True)),
        "video_source": video.video_source or "",
        "source_url": video.source_url or "",
        "has_subtitle": bool(video.srt_path),
    }
    if include_filename:
        payload["filename"] = video.url or ""
    return payload


def _find_video(
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
) -> Video | None:
    qs = Video.objects.select_related("category").prefetch_related("tags")
    if video_id is not None:
        return qs.filter(id=video_id).first()
    if filename:
        return qs.filter(url=filename).first()
    if title:
        return qs.filter(name__iexact=title).first() or qs.filter(
            name__icontains=title
        ).first()
    return None


def _resolve_video_sync(
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    if video_id is None and not filename and not title:
        return {
            "success": False,
            "error": "Provide one of video_id, filename, or title",
        }
    video = _find_video(video_id=video_id, filename=filename, title=title)
    if video is None:
        return {"success": False, "error": "video not found"}
    return {"success": True, "video": _video_payload(video, include_filename=True)}


async def _resolve_video(
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    return await _run_sync(_resolve_video_sync, video_id, filename, title)


def _api_base_url() -> str:
    base = (
        os.environ.get("VIDGO_INTERNAL_API_BASE")
        or os.environ.get("VIDGO_API_BASE")
        or f"http://127.0.0.1:{os.environ.get('PORT', '8080')}"
    )
    return base.rstrip("/")


def _authorization_from_context(ctx: Context | None) -> str:
    if ctx is not None:
        try:
            request = ctx.request_context.request
        except ValueError:
            request = None
        headers = getattr(request, "headers", None)
        if headers is not None:
            authorization = headers.get("authorization") or headers.get("Authorization")
            if authorization:
                return authorization

    token = os.environ.get("VIDGO_API_TOKEN", "").strip()
    return f"Bearer {token}" if token else ""


def _api_request_sync(
    authorization: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    if not authorization:
        return {
            "success": False,
            "error": "No Bearer token available for internal VidGo API call",
        }

    data = None
    headers = {
        "Accept": "application/json",
        "Authorization": authorization,
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(
        f"{_api_base_url()}{path}",
        data=data,
        headers=headers,
        method=method.upper(),
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            body = json.loads(raw) if raw else {}
            result = {
                "success": True,
                "http_status": response.status,
            }
            if isinstance(body, dict):
                result.update(body)
            else:
                result["data"] = body
            return result
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"raw": raw}
        error = body.get("error") if isinstance(body, dict) else None
        return {
            "success": False,
            "http_status": exc.code,
            "error": error or exc.reason,
            "data": body,
        }
    except URLError as exc:
        return {"success": False, "error": f"VidGo API unavailable: {exc.reason}"}
    except TimeoutError:
        return {"success": False, "error": "VidGo API request timed out"}


async def _call_vidgo_api(
    ctx: Context | None,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    authorization = _authorization_from_context(ctx)
    return await _run_blocking(
        _api_request_sync,
        authorization,
        method,
        path,
        payload,
        timeout,
    )


mcp = FastMCP(
    "VidGo",
    instructions=(
        "Use these tools to search VidGo videos, inspect video metadata, submit "
        "long-running summary tasks, poll progress by task_id, fetch summaries, "
        "and ask questions about completed video-understanding databases."
    ),
    streamable_http_path="/mcp",
    sse_path="/sse",
    message_path="/messages/",
    stateless_http=False,
    transport_security=_transport_security_settings(),
)


@mcp.tool()
async def test_connection() -> str:
    """Check that the VidGo MCP server can access the VidGo database."""
    return await _run_sync(_test_connection_sync)


def _test_connection_sync() -> str:
    return _json(
        {
            "success": True,
            "service": "VidGo MCP",
            "video_count": Video.objects.count(),
        }
    )


@mcp.tool()
async def list_videos(
    limit: int = 50,
    offset: int = 0,
    include_filenames: bool = True,
) -> str:
    """List VidGo videos ordered by most recently modified.

    Args:
        limit: Maximum number of videos to return. Values above 200 are clamped.
        offset: Number of videos to skip.
        include_filenames: Include stored media filenames for follow-up API calls.
    """
    return await _run_sync(_list_videos_sync, limit, offset, include_filenames)


def _list_videos_sync(limit: int, offset: int, include_filenames: bool) -> str:
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    qs = (
        Video.objects.select_related("category")
        .prefetch_related("tags")
        .order_by("-last_modified")
    )
    total = qs.count()
    videos = [
        _video_payload(v, include_filename=include_filenames)
        for v in qs[offset : offset + limit]
    ]
    return _json(
        {
            "success": True,
            "total": total,
            "offset": offset,
            "limit": limit,
            "videos": videos,
        }
    )


@mcp.tool()
async def search_videos(query: str, mode: str = "title", limit: int = 20) -> str:
    """Search VidGo videos by title or subtitle/content.

    Args:
        query: Keyword, title, or phrase to search for.
        mode: Search mode. Use "title" for title-only, or "title_content" to
            also scan subtitles and notes.
        limit: Maximum number of results to return. Values above 100 are clamped.
    """
    return await _run_sync(_search_videos_sync, query, mode, limit)


def _search_videos_sync(query: str, mode: str, limit: int) -> str:
    query = (query or "").strip()
    if not query:
        return _json({"success": False, "error": "query is required", "results": []})

    if mode not in {"title", "subtitle", "title_content"}:
        return _json(
            {
                "success": False,
                "error": "mode must be one of: title, subtitle, title_content",
                "results": [],
            }
        )

    limit = max(1, min(int(limit), 100))
    results, total_matches, truncated = VideoSearchView().get_search_results(
        query,
        mode=mode,
        limit=limit,
    )
    return _json(
        {
            "success": True,
            "query": query,
            "mode": mode,
            "total_matches": total_matches,
            "truncated": truncated or len(results) >= limit,
            "results": results[:limit],
        }
    )


@mcp.tool()
async def get_video_info(
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
) -> str:
    """Get metadata for one VidGo video by id, stored filename, or title.

    Args:
        video_id: Numeric VidGo video id. Preferred when available.
        filename: Stored media filename from list_videos/search_videos.
        title: Exact or partial human-readable video title.
    """
    return await _run_sync(_get_video_info_sync, video_id, filename, title)


def _get_video_info_sync(
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
) -> str:
    return _json(_resolve_video_sync(video_id, filename, title))


@mcp.tool()
async def check_summary_prerequisites(
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
    ctx: Context | None = None,
) -> str:
    """Check whether a video has subtitles and language metadata for summary.

    Args:
        video_id: Numeric VidGo video id. Preferred when available.
        filename: Stored media filename from list_videos/search_videos.
        title: Exact or partial human-readable video title.
    """
    resolved = await _resolve_video(video_id, filename, title)
    if not resolved.get("success"):
        return _json(resolved)
    video = resolved["video"]
    path = f"/api/video-summary/{quote(video['filename'], safe='')}/prerequisites"
    result = await _call_vidgo_api(ctx, "GET", path)
    return _json(result)


@mcp.tool()
async def submit_summary_task(
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
    language: str = "中文",
    min_coverage: float | None = None,
    ctx: Context | None = None,
) -> str:
    """Submit a long-running video summary task and return its task_id.

    The task is processed by the main VidGo API process. Poll with
    get_summary_status(task_id) until status is Completed or Failed.

    Args:
        video_id: Numeric VidGo video id. Preferred when available.
        filename: Stored media filename from list_videos/search_videos.
        title: Exact or partial human-readable video title.
        language: Summary language, for example "中文" or "English".
        min_coverage: Optional slide/frame coverage threshold. Omit for server default.
    """
    resolved = await _resolve_video(video_id, filename, title)
    if not resolved.get("success"):
        return _json(resolved)

    payload: dict[str, Any] = {
        "video_id": resolved["video"]["id"],
        "language": language,
    }
    if min_coverage is not None:
        payload["min_coverage"] = max(0.0, min(1.0, float(min_coverage)))

    result = await _call_vidgo_api(ctx, "POST", "/api/summary/add", payload)
    if result.get("success"):
        result["next_step"] = "Call get_summary_status with the returned task_id."
    return _json(result)


@mcp.tool()
async def get_summary_status(
    task_id: str | None = None,
    ctx: Context | None = None,
) -> str:
    """Get one summary task status, or all in-memory summary task statuses.

    Args:
        task_id: Task id returned by submit_summary_task. Omit to list all tasks.
    """
    if task_id:
        path = f"/api/summary/{quote(task_id, safe='')}/status"
    else:
        path = "/api/summary/status"
    return _json(await _call_vidgo_api(ctx, "GET", path))


@mcp.tool()
async def get_summary_result(
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
    max_chars: int = 20000,
    ctx: Context | None = None,
) -> str:
    """Fetch a completed video summary.

    Args:
        video_id: Numeric VidGo video id. Preferred when available.
        filename: Stored media filename from list_videos/search_videos.
        title: Exact or partial human-readable video title.
        max_chars: Truncate summary text above this many characters. Use 0 for full text.
    """
    resolved = await _resolve_video(video_id, filename, title)
    if not resolved.get("success"):
        return _json(resolved)

    video = resolved["video"]
    path = f"/api/video-summary/{quote(video['filename'], safe='')}"
    result = await _call_vidgo_api(ctx, "GET", path, timeout=120)
    summary = result.get("summary")
    if isinstance(summary, str) and max_chars and len(summary) > max_chars:
        result["summary"] = summary[:max_chars]
        result["truncated"] = True
        result["summary_chars"] = len(summary)
    return _json(result)


@mcp.tool()
async def ask_video(
    question: str,
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
    ctx: Context | None = None,
) -> str:
    """Ask a question about a video that already has a VidUnder summary database.

    Args:
        question: Natural-language question to ask about the video.
        video_id: Numeric VidGo video id. Preferred when available.
        filename: Stored media filename from list_videos/search_videos.
        title: Exact or partial human-readable video title.
    """
    if not question.strip():
        return _json({"success": False, "error": "question is required"})

    resolved = await _resolve_video(video_id, filename, title)
    if not resolved.get("success"):
        return _json(resolved)

    video = resolved["video"]
    path = f"/api/video-ask/{quote(video['filename'], safe='')}"
    result = await _call_vidgo_api(
        ctx,
        "POST",
        path,
        {"question": question.strip()},
        timeout=600,
    )
    return _json(result)


def streamable_http_app():
    """Return the Streamable HTTP ASGI app."""
    return mcp.streamable_http_app()


def sse_app():
    """Return the legacy SSE ASGI app."""
    return mcp.sse_app()
