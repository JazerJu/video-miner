"""VidGo MCP tools exposed through the optional ASGI MCP process."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlparse

from asgiref.sync import sync_to_async
from django.db import close_old_connections
from mcp.server.fastmcp import FastMCP
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


mcp = FastMCP(
    "VidGo",
    instructions=(
        "Use these tools to search VidGo videos, inspect video metadata, and "
        "orchestrate VidGo workflows. Long-running work must be submitted first "
        "and then polled by the returned task key."
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
    qs = Video.objects.select_related("category").prefetch_related("tags")
    video: Video | None = None

    if video_id is not None:
        video = qs.filter(id=video_id).first()
    elif filename:
        video = qs.filter(url=filename).first()
    elif title:
        video = qs.filter(name__iexact=title).first() or qs.filter(
            name__icontains=title
        ).first()
    else:
        return _json(
            {
                "success": False,
                "error": "Provide one of video_id, filename, or title",
            }
        )

    if video is None:
        return _json({"success": False, "error": "video not found"})

    return _json({"success": True, "video": _video_payload(video, include_filename=True)})


def streamable_http_app():
    """Return the Streamable HTTP ASGI app."""
    return mcp.streamable_http_app()


def sse_app():
    """Return the legacy SSE ASGI app."""
    return mcp.sse_app()
