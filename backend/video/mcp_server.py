"""VidGo MCP tools exposed through the optional ASGI MCP process."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from asgiref.sync import sync_to_async
from django.db import close_old_connections, transaction
from django.db.models import Count
from django.utils import timezone
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.server import TransportSecuritySettings

from video.models import Category, Tag, Video
from video.tag_colors import get_random_tag_color
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
        "category_id": video.category_id,
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
            success = True
            if isinstance(body, dict) and "success" in body:
                success = bool(body.get("success"))
            elif isinstance(body, dict) and body.get("error"):
                success = False
            result = {
                "success": success,
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


LANGUAGE_ALIASES = {
    "ja": "jp",
    "jpn": "jp",
    "jp": "jp",
    "zh": "zh",
    "cn": "zh",
    "chinese": "zh",
    "en": "en",
    "english": "en",
    "de": "de",
    "german": "de",
}
SUBTITLE_LANGUAGES = {"zh", "en", "jp", "de"}
MODEL_ALIASES = {
    "funasr": "fun-asr",
    "fun-asr": "fun-asr",
    "fun-asr-nano": "fun-asr",
    "glm-asr": "glm-asr",
    "glm asr": "glm-asr",
    "glm-asr stack": "glm-asr",
    "minicpm": "minicpm-v4.5",
    "minicpm-v": "minicpm-v4.5",
    "minicpm-v4.5": "minicpm-v4.5",
    "glm-ocr": "glm-ocr",
    "ocr": "glm-ocr",
    "embedding": "embedding",
    "bge": "embedding",
}
SENSITIVE_KEY_PARTS = ("api_key", "sessdata", "token", "secret", "password")


def _normalize_subtitle_lang(value: str | None) -> str:
    key = (value or "").strip().lower()
    return LANGUAGE_ALIASES.get(key, key)


def _normalize_translation_lang(value: str | None) -> str:
    key = (value or "").strip()
    if not key or key.lower() in {"none", "no", "false", "null"}:
        return "None"
    return _normalize_subtitle_lang(key)


def _normalize_model_name(model_name: str) -> str:
    key = (model_name or "").strip().lower()
    return MODEL_ALIASES.get(key, key)


def _redact_settings(data: Any) -> Any:
    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            lowered = str(key).lower()
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                redacted[key] = bool(value)
            else:
                redacted[key] = _redact_settings(value)
        return redacted
    if isinstance(data, list):
        return [_redact_settings(item) for item in data]
    return data


async def _resolve_video_for_task(
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    resolved = await _resolve_video(video_id, filename, title)
    if not resolved.get("success"):
        return resolved
    video = resolved["video"]
    if not video.get("id") or not video.get("title"):
        return {"success": False, "error": "resolved video is missing id or title"}
    return resolved


def _tag_payload(tag: Tag, video_count: int | None = None) -> dict[str, Any]:
    count = video_count
    if count is None:
        count = tag.videos.count()
    return {
        "id": tag.id,
        "name": tag.name,
        "color": tag.color,
        "video_count": count,
    }


def _category_payload(
    category: Category,
    video_count: int | None = None,
) -> dict[str, Any]:
    count = video_count
    if count is None:
        count = category.categories.count()
    return {
        "id": category.id,
        "name": category.name,
        "video_count": count,
    }


def _clean_name_list(names: list[str] | None) -> list[str]:
    cleaned = []
    seen = set()
    for name in names or []:
        text = str(name).strip()
        if text and text not in seen:
            cleaned.append(text)
            seen.add(text)
    return cleaned


def _find_tag(tag_id: int | None = None, name: str | None = None) -> Tag | None:
    if tag_id is not None:
        return Tag.objects.filter(id=tag_id).first()
    if name:
        return Tag.objects.filter(name__iexact=name.strip()).first()
    return None


def _find_category(
    category_id: int | None = None,
    name: str | None = None,
) -> Category | None:
    if category_id is not None:
        return Category.objects.filter(id=category_id).first()
    if name:
        return Category.objects.filter(name__iexact=name.strip()).first()
    return None


def _resolve_target_videos(
    video_ids: list[int] | None = None,
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
) -> tuple[list[Video], dict[str, Any] | None]:
    requested_ids = []
    for item in video_ids or []:
        try:
            requested_ids.append(int(item))
        except (TypeError, ValueError):
            return [], {"success": False, "error": f"invalid video id: {item}"}
    if video_id is not None:
        requested_ids.append(int(video_id))

    resolved_by_text = None
    if filename or title:
        resolved_by_text = _find_video(filename=filename, title=title)
        if resolved_by_text is None:
            return [], {"success": False, "error": "video not found"}
        requested_ids.append(resolved_by_text.id)

    requested_ids = list(dict.fromkeys(requested_ids))
    if not requested_ids:
        return [], {
            "success": False,
            "error": "Provide video_ids, video_id, filename, or title",
        }

    videos = list(
        Video.objects.select_related("category")
        .prefetch_related("tags")
        .filter(id__in=requested_ids)
    )
    found_ids = {video.id for video in videos}
    missing_ids = [item for item in requested_ids if item not in found_ids]
    if missing_ids:
        return [], {
            "success": False,
            "error": "video not found",
            "missing_ids": missing_ids,
        }
    return videos, None


mcp = FastMCP(
    "VidGo",
    instructions=(
        "Use these tools to search VidGo videos, inspect video metadata, submit "
        "long-running summary tasks, poll progress by task_id, fetch summaries, "
        "ask questions about completed video-understanding databases, generate "
        "subtitles, download source videos, organize videos with tags/categories, "
        "and inspect model readiness."
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
async def list_tags() -> str:
    """List all video tags with colors and usage counts."""
    return await _run_sync(_list_tags_sync)


def _list_tags_sync() -> str:
    tags = Tag.objects.annotate(video_count=Count("videos")).order_by("name")
    return _json(
        {
            "success": True,
            "tags": [
                _tag_payload(tag, video_count=tag.video_count)
                for tag in tags
            ],
        }
    )


@mcp.tool()
async def create_tag(name: str, color: str | None = None) -> str:
    """Create a tag, or return the existing matching tag.

    Args:
        name: Tag name.
        color: Optional hex color such as #3B82F6. If omitted, VidGo assigns one.
    """
    return await _run_sync(_create_tag_sync, name, color)


def _create_tag_sync(name: str, color: str | None = None) -> str:
    tag_name = (name or "").strip()
    if not tag_name:
        return _json({"success": False, "error": "name is required"})

    existing = Tag.objects.filter(name__iexact=tag_name).first()
    if existing:
        return _json(
            {
                "success": True,
                "created": False,
                "tag": _tag_payload(existing),
            }
        )

    tag = Tag.objects.create(
        name=tag_name,
        color=(color or "").strip()
        or get_random_tag_color(Tag.objects.values_list("color", flat=True)),
    )
    return _json({"success": True, "created": True, "tag": _tag_payload(tag)})


@mcp.tool()
async def update_tag(
    tag_id: int | None = None,
    name: str | None = None,
    new_name: str | None = None,
    color: str | None = None,
) -> str:
    """Rename or recolor a tag.

    Args:
        tag_id: Numeric tag id. Preferred when available.
        name: Existing tag name if tag_id is not provided.
        new_name: Optional replacement tag name.
        color: Optional replacement hex color.
    """
    return await _run_sync(_update_tag_sync, tag_id, name, new_name, color)


def _update_tag_sync(
    tag_id: int | None = None,
    name: str | None = None,
    new_name: str | None = None,
    color: str | None = None,
) -> str:
    tag = _find_tag(tag_id=tag_id, name=name)
    if tag is None:
        return _json({"success": False, "error": "tag not found"})

    clean_new_name = (new_name or "").strip()
    if clean_new_name and clean_new_name.lower() != tag.name.lower():
        if Tag.objects.filter(name__iexact=clean_new_name).exclude(id=tag.id).exists():
            return _json({"success": False, "error": "tag name already exists"})
        tag.name = clean_new_name

    clean_color = (color or "").strip()
    if clean_color:
        tag.color = clean_color

    tag.save()
    return _json({"success": True, "tag": _tag_payload(tag)})


@mcp.tool()
async def delete_tag(tag_id: int | None = None, name: str | None = None) -> str:
    """Delete a tag without deleting any videos.

    Args:
        tag_id: Numeric tag id. Preferred when available.
        name: Tag name if tag_id is not provided.
    """
    return await _run_sync(_delete_tag_sync, tag_id, name)


def _delete_tag_sync(tag_id: int | None = None, name: str | None = None) -> str:
    tag = _find_tag(tag_id=tag_id, name=name)
    if tag is None:
        return _json({"success": False, "error": "tag not found"})
    payload = _tag_payload(tag)
    affected_videos = tag.videos.count()
    tag.delete()
    return _json(
        {
            "success": True,
            "deleted": payload,
            "affected_videos": affected_videos,
            "video_deleted": False,
        }
    )


@mcp.tool()
async def merge_tags(
    source_tag_id: int | None = None,
    source_name: str | None = None,
    target_tag_id: int | None = None,
    target_name: str | None = None,
) -> str:
    """Merge one tag into another tag, then delete the source tag.

    Args:
        source_tag_id: Source tag id.
        source_name: Source tag name if id is not provided.
        target_tag_id: Target tag id.
        target_name: Target tag name if id is not provided.
    """
    return await _run_sync(
        _merge_tags_sync,
        source_tag_id,
        source_name,
        target_tag_id,
        target_name,
    )


def _merge_tags_sync(
    source_tag_id: int | None = None,
    source_name: str | None = None,
    target_tag_id: int | None = None,
    target_name: str | None = None,
) -> str:
    source = _find_tag(tag_id=source_tag_id, name=source_name)
    target = _find_tag(tag_id=target_tag_id, name=target_name)
    if source is None:
        return _json({"success": False, "error": "source tag not found"})
    if target is None:
        return _json({"success": False, "error": "target tag not found"})
    if source.id == target.id:
        return _json({"success": False, "error": "source and target are the same tag"})

    with transaction.atomic():
        videos = list(source.videos.all())
        for video in videos:
            video.tags.add(target)
        source_payload = _tag_payload(source, video_count=len(videos))
        target_payload = _tag_payload(target)
        source.delete()

    return _json(
        {
            "success": True,
            "merged_video_count": len(videos),
            "deleted_source": source_payload,
            "target": target_payload,
            "video_deleted": False,
        }
    )


@mcp.tool()
async def add_video_tags(
    tag_names: list[str],
    video_ids: list[int] | None = None,
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
) -> str:
    """Add tags to one or more videos, creating tags if needed.

    Args:
        tag_names: Tag names to add.
        video_ids: Numeric video ids for batch updates.
        video_id: Single numeric video id.
        filename: Stored media filename from list_videos/search_videos.
        title: Exact or partial video title.
    """
    return await _run_sync(
        _add_video_tags_sync,
        tag_names,
        video_ids,
        video_id,
        filename,
        title,
    )


def _get_or_create_tags(tag_names: list[str]) -> list[Tag]:
    tags = []
    for tag_name in _clean_name_list(tag_names):
        tag = Tag.objects.filter(name__iexact=tag_name).first()
        if tag is None:
            tag = Tag.objects.create(
                name=tag_name,
                color=get_random_tag_color(Tag.objects.values_list("color", flat=True)),
            )
        tags.append(tag)
    return tags


def _add_video_tags_sync(
    tag_names: list[str],
    video_ids: list[int] | None = None,
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
) -> str:
    tags = _get_or_create_tags(tag_names)
    if not tags:
        return _json({"success": False, "error": "tag_names is required"})

    videos, error = _resolve_target_videos(video_ids, video_id, filename, title)
    if error:
        return _json(error)

    with transaction.atomic():
        for video in videos:
            video.tags.add(*tags)

    return _json(
        {
            "success": True,
            "updated_video_count": len(videos),
            "tags": [_tag_payload(tag) for tag in tags],
            "videos": [_video_payload(video) for video in videos],
        }
    )


@mcp.tool()
async def set_video_tags(
    tag_names: list[str],
    video_ids: list[int] | None = None,
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
) -> str:
    """Replace all tags on one or more videos, creating tags if needed.

    Args:
        tag_names: Complete desired tag list. Use [] to clear all tags.
        video_ids: Numeric video ids for batch updates.
        video_id: Single numeric video id.
        filename: Stored media filename from list_videos/search_videos.
        title: Exact or partial video title.
    """
    return await _run_sync(
        _set_video_tags_sync,
        tag_names,
        video_ids,
        video_id,
        filename,
        title,
    )


def _set_video_tags_sync(
    tag_names: list[str],
    video_ids: list[int] | None = None,
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
) -> str:
    tags = _get_or_create_tags(tag_names)
    videos, error = _resolve_target_videos(video_ids, video_id, filename, title)
    if error:
        return _json(error)

    with transaction.atomic():
        for video in videos:
            video.tags.set(tags)

    return _json(
        {
            "success": True,
            "updated_video_count": len(videos),
            "tags": [_tag_payload(tag) for tag in tags],
            "videos": [_video_payload(video) for video in videos],
        }
    )


@mcp.tool()
async def remove_video_tags(
    tag_names: list[str],
    video_ids: list[int] | None = None,
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
) -> str:
    """Remove tags from one or more videos without deleting the tag objects.

    Args:
        tag_names: Tag names to remove.
        video_ids: Numeric video ids for batch updates.
        video_id: Single numeric video id.
        filename: Stored media filename from list_videos/search_videos.
        title: Exact or partial video title.
    """
    return await _run_sync(
        _remove_video_tags_sync,
        tag_names,
        video_ids,
        video_id,
        filename,
        title,
    )


def _remove_video_tags_sync(
    tag_names: list[str],
    video_ids: list[int] | None = None,
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
) -> str:
    names = _clean_name_list(tag_names)
    if not names:
        return _json({"success": False, "error": "tag_names is required"})
    tags = []
    missing_names = []
    for name in names:
        tag = Tag.objects.filter(name__iexact=name).first()
        if tag is None:
            missing_names.append(name)
        else:
            tags.append(tag)
    if not tags:
        return _json(
            {
                "success": False,
                "error": "no matching tags found",
                "missing_tag_names": missing_names,
            }
        )

    videos, error = _resolve_target_videos(video_ids, video_id, filename, title)
    if error:
        return _json(error)

    with transaction.atomic():
        for video in videos:
            video.tags.remove(*tags)

    return _json(
        {
            "success": True,
            "updated_video_count": len(videos),
            "removed_tags": [_tag_payload(tag) for tag in tags],
            "missing_tag_names": missing_names,
            "videos": [_video_payload(video) for video in videos],
        }
    )


@mcp.tool()
async def list_categories(include_videos: bool = False, video_limit: int = 20) -> str:
    """List categories with usage counts.

    Args:
        include_videos: Include sample videos for each category and unarchived videos.
        video_limit: Maximum videos per category when include_videos is true.
    """
    return await _run_sync(_list_categories_sync, include_videos, video_limit)


def _list_categories_sync(include_videos: bool = False, video_limit: int = 20) -> str:
    video_limit = max(1, min(int(video_limit), 100))
    categories = Category.objects.annotate(video_count=Count("categories")).order_by(
        "id"
    )
    payload = []
    for category in categories:
        item = _category_payload(category, video_count=category.video_count)
        if include_videos:
            videos = (
                Video.objects.filter(category=category)
                .select_related("category")
                .prefetch_related("tags")
                .order_by("-last_modified")[:video_limit]
            )
            item["videos"] = [_video_payload(video) for video in videos]
        payload.append(item)

    unarchived_count = Video.objects.filter(category__isnull=True).count()
    result: dict[str, Any] = {
        "success": True,
        "categories": payload,
        "unarchived": {
            "id": None,
            "name": "unarchived",
            "video_count": unarchived_count,
        },
    }
    if include_videos:
        videos = (
            Video.objects.filter(category__isnull=True)
            .select_related("category")
            .prefetch_related("tags")
            .order_by("-last_modified")[:video_limit]
        )
        result["unarchived"]["videos"] = [_video_payload(video) for video in videos]
    return _json(result)


@mcp.tool()
async def create_category(name: str) -> str:
    """Create a category, or return the existing matching category."""
    return await _run_sync(_create_category_sync, name)


def _create_category_sync(name: str) -> str:
    category_name = (name or "").strip()
    if not category_name:
        return _json({"success": False, "error": "name is required"})

    existing = Category.objects.filter(name__iexact=category_name).first()
    if existing:
        return _json(
            {
                "success": True,
                "created": False,
                "category": _category_payload(existing),
            }
        )

    category = Category.objects.create(name=category_name, created_time=timezone.now())
    return _json(
        {"success": True, "created": True, "category": _category_payload(category)}
    )


@mcp.tool()
async def update_category(
    category_id: int | None = None,
    name: str | None = None,
    new_name: str | None = None,
) -> str:
    """Rename a category.

    Args:
        category_id: Numeric category id. Preferred when available.
        name: Existing category name if category_id is not provided.
        new_name: Replacement category name.
    """
    return await _run_sync(_update_category_sync, category_id, name, new_name)


def _update_category_sync(
    category_id: int | None = None,
    name: str | None = None,
    new_name: str | None = None,
) -> str:
    category = _find_category(category_id=category_id, name=name)
    if category is None:
        return _json({"success": False, "error": "category not found"})

    category_name = (new_name or "").strip()
    if not category_name:
        return _json({"success": False, "error": "new_name is required"})

    if category_name.lower() != category.name.lower():
        if (
            Category.objects.filter(name__iexact=category_name)
            .exclude(id=category.id)
            .exists()
        ):
            return _json({"success": False, "error": "category name already exists"})
        category.name = category_name
        category.save(update_fields=["name"])

    return _json({"success": True, "category": _category_payload(category)})


@mcp.tool()
async def delete_category(
    category_id: int | None = None,
    name: str | None = None,
) -> str:
    """Delete a category without deleting videos.

    Videos in the deleted category become unarchived.

    Args:
        category_id: Numeric category id. Preferred when available.
        name: Category name if category_id is not provided.
    """
    return await _run_sync(_delete_category_sync, category_id, name)


def _delete_category_sync(
    category_id: int | None = None,
    name: str | None = None,
) -> str:
    category = _find_category(category_id=category_id, name=name)
    if category is None:
        return _json({"success": False, "error": "category not found"})

    payload = _category_payload(category)
    affected_videos = Video.objects.filter(category=category).count()
    with transaction.atomic():
        Video.objects.filter(category=category).update(category=None)
        category.delete()
    return _json(
        {
            "success": True,
            "deleted": payload,
            "affected_videos": affected_videos,
            "video_deleted": False,
        }
    )


@mcp.tool()
async def set_video_category(
    category_id: int | None = None,
    category_name: str | None = None,
    create_if_missing: bool = True,
    clear: bool = False,
    video_ids: list[int] | None = None,
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
) -> str:
    """Move one or more videos into a category, or clear their category.

    Args:
        category_id: Target category id.
        category_name: Target category name if category_id is not provided.
        create_if_missing: Create category_name if it does not exist.
        clear: Set category to unarchived and ignore category_id/category_name.
        video_ids: Numeric video ids for batch updates.
        video_id: Single numeric video id.
        filename: Stored media filename from list_videos/search_videos.
        title: Exact or partial video title.
    """
    return await _run_sync(
        _set_video_category_sync,
        category_id,
        category_name,
        create_if_missing,
        clear,
        video_ids,
        video_id,
        filename,
        title,
    )


def _set_video_category_sync(
    category_id: int | None = None,
    category_name: str | None = None,
    create_if_missing: bool = True,
    clear: bool = False,
    video_ids: list[int] | None = None,
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
) -> str:
    videos, error = _resolve_target_videos(video_ids, video_id, filename, title)
    if error:
        return _json(error)

    category = None
    created = False
    if not clear:
        category = _find_category(category_id=category_id, name=category_name)
        clean_name = (category_name or "").strip()
        if category is None and clean_name and create_if_missing:
            category = Category.objects.create(
                name=clean_name,
                created_time=timezone.now(),
            )
            created = True
        if category is None:
            return _json(
                {
                    "success": False,
                    "error": "category not found",
                    "hint": "Provide category_id/category_name or set clear=true.",
                }
            )

    with transaction.atomic():
        Video.objects.filter(id__in=[video.id for video in videos]).update(
            category=category
        )

    refreshed = list(
        Video.objects.select_related("category")
        .prefetch_related("tags")
        .filter(id__in=[video.id for video in videos])
    )
    return _json(
        {
            "success": True,
            "updated_video_count": len(refreshed),
            "category": _category_payload(category) if category else None,
            "category_created": created,
            "videos": [_video_payload(video) for video in refreshed],
        }
    )


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


@mcp.tool()
async def query_download_url(url: str, ctx: Context | None = None) -> str:
    """Resolve a Bilibili, YouTube, or Apple Podcasts URL before downloading.

    Args:
        url: Source media URL.
    """
    if not url.strip():
        return _json({"success": False, "error": "url is required"})
    return _json(
        await _call_vidgo_api(ctx, "POST", "/api/stream_media/query", {"url": url})
    )


@mcp.tool()
async def start_download(
    url: str,
    bvid: str | None = None,
    cids: list[str] | None = None,
    parts: list[str] | None = None,
    filename: str | None = None,
    durations: list[int] | None = None,
    ctx: Context | None = None,
) -> str:
    """Start downloading a resolved source URL.

    If bvid/cids/parts/filename are omitted, the tool queries the URL first and
    downloads all returned parts. Poll with get_download_status.

    Args:
        url: Source Bilibili, YouTube, or Apple Podcasts URL.
        bvid: Bilibili bvid, YouTube id, or podcast episode id.
        cids: Bilibili part cids. Omit to download all queried parts.
        parts: Human-readable part names. Omit to use query results.
        filename: Base title for downloaded media.
        durations: Optional per-part durations in seconds.
    """
    if not url.strip():
        return _json({"success": False, "error": "url is required"})

    query_info: dict[str, Any] | None = None
    if not bvid or not filename or ("bilibili" in url and (not cids or not parts)):
        query_info = await _call_vidgo_api(
            ctx,
            "POST",
            "/api/stream_media/query",
            {"url": url},
            timeout=120,
        )
        if not query_info.get("success"):
            return _json(query_info)
        bvid = bvid or query_info.get("bvid")
        filename = filename or query_info.get("title")

    payload: dict[str, Any] = {
        "url": url,
        "bvid": bvid,
        "filename": filename,
    }

    if "bilibili" in url:
        video_data = (query_info or {}).get("video_data") or []
        if not cids:
            cids = [str(item.get("cid")) for item in video_data if item.get("cid")]
        if not parts:
            parts = [
                str(item.get("part") or item.get("title") or item.get("page") or idx)
                for idx, item in enumerate(video_data, start=1)
            ]
        if not durations:
            durations = [
                int(item.get("duration") or 0)
                for item in video_data
                if item.get("duration") is not None
            ]
        payload.update({"cids": cids or [], "parts": parts or []})
        if durations:
            payload["durations"] = durations

    result = await _call_vidgo_api(
        ctx,
        "POST",
        "/api/stream_media/download/add",
        payload,
        timeout=120,
    )
    if result.get("success") and result.get("task_ids"):
        result["next_step"] = "Call get_download_status for each task_id in task_ids."
    elif result.get("success") and "task_id" not in result:
        result["next_step"] = "Call get_download_status and match by title or source URL."
    elif result.get("success"):
        result["next_step"] = "Call get_download_status with the returned task_id."
    return _json(result)


@mcp.tool()
async def get_download_status(
    task_id: str | None = None,
    ctx: Context | None = None,
) -> str:
    """Get one download task status, or all active download task statuses.

    Args:
        task_id: Download task id. Omit to list all download statuses.
    """
    path = (
        f"/api/stream_media/download/{quote(task_id, safe='')}/status"
        if task_id
        else "/api/stream_media/download_status"
    )
    return _json(await _call_vidgo_api(ctx, "GET", path))


@mcp.tool()
async def retry_download_task(task_id: str, ctx: Context | None = None) -> str:
    """Retry a failed or queued download task by task_id."""
    if not task_id.strip():
        return _json({"success": False, "error": "task_id is required"})
    path = f"/api/stream_media/download/{quote(task_id, safe='')}/retry"
    return _json(await _call_vidgo_api(ctx, "POST", path))


@mcp.tool()
async def delete_download_task(task_id: str, ctx: Context | None = None) -> str:
    """Delete a download task by task_id."""
    if not task_id.strip():
        return _json({"success": False, "error": "task_id is required"})
    path = f"/api/stream_media/download/{quote(task_id, safe='')}/delete"
    return _json(await _call_vidgo_api(ctx, "DELETE", path))


@mcp.tool()
async def start_subtitle_generation(
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
    src_lang: str = "en",
    trans_lang: str = "None",
    emphasize_dst: str = "",
    ctx: Context | None = None,
) -> str:
    """Start original subtitle generation, optionally with translation.

    Subtitle tasks do not have a separate task_id; poll by numeric video_id.

    Args:
        video_id: Numeric VidGo video id. Preferred when available.
        filename: Stored media filename from list_videos/search_videos.
        title: Exact or partial human-readable video title.
        src_lang: Original language: zh, en, jp, or de. ja is accepted as jp.
        trans_lang: Translation language zh/en/jp/de, or None for original only.
        emphasize_dst: Optional glossary or terms to emphasize during translation.
    """
    source_lang = _normalize_subtitle_lang(src_lang)
    target_lang = _normalize_translation_lang(trans_lang)
    if source_lang not in SUBTITLE_LANGUAGES:
        return _json({"success": False, "error": "src_lang must be zh, en, jp, or de"})
    if target_lang != "None" and target_lang not in SUBTITLE_LANGUAGES:
        return _json(
            {"success": False, "error": "trans_lang must be None, zh, en, jp, or de"}
        )

    resolved = await _resolve_video_for_task(video_id, filename, title)
    if not resolved.get("success"):
        return _json(resolved)
    video = resolved["video"]
    payload = {
        "video_id_list": [video["id"]],
        "video_name_list": [video["title"]],
        "src_lang": source_lang,
        "trans_lang": target_lang,
        "emphasize_dst": emphasize_dst or "",
    }
    result = await _call_vidgo_api(
        ctx,
        "POST",
        "/api/tasks/subtitle_generate/add",
        payload,
    )
    if result.get("success"):
        result["polling_key"] = video["id"]
        result["next_step"] = "Call get_subtitle_status with this video_id."
    return _json(result)


@mcp.tool()
async def start_subtitle_translation(
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
    target_lang: str = "zh",
    emphasize_dst: str = "",
    ctx: Context | None = None,
) -> str:
    """Translate an existing original subtitle track into another language.

    Args:
        video_id: Numeric VidGo video id. Preferred when available.
        filename: Stored media filename from list_videos/search_videos.
        title: Exact or partial human-readable video title.
        target_lang: Translation language: zh, en, jp, or de. ja is accepted as jp.
        emphasize_dst: Optional glossary or terms to emphasize during translation.
    """
    normalized_target = _normalize_subtitle_lang(target_lang)
    if normalized_target not in SUBTITLE_LANGUAGES:
        return _json(
            {"success": False, "error": "target_lang must be zh, en, jp, or de"}
        )

    resolved = await _resolve_video_for_task(video_id, filename, title)
    if not resolved.get("success"):
        return _json(resolved)
    video = resolved["video"]
    payload = {
        "video_id_list": [video["id"]],
        "video_name_list": [video["title"]],
        "target_lang": normalized_target,
        "emphasize_dst": emphasize_dst or "",
    }
    result = await _call_vidgo_api(
        ctx,
        "POST",
        "/api/tasks/subtitle_translation/add",
        payload,
    )
    if result.get("success"):
        result["polling_key"] = video["id"]
        result["next_step"] = "Call get_subtitle_status with this video_id."
    return _json(result)


@mcp.tool()
async def get_subtitle_status(
    video_id: int | None = None,
    filename: str | None = None,
    title: str | None = None,
    ctx: Context | None = None,
) -> str:
    """Get subtitle task status for one video, or all subtitle task statuses.

    Args:
        video_id: Numeric VidGo video id. Omit all identifiers to list all tasks.
        filename: Stored media filename from list_videos/search_videos.
        title: Exact or partial human-readable video title.
    """
    resolved_video_id = video_id
    if resolved_video_id is None and (filename or title):
        resolved = await _resolve_video_for_task(None, filename, title)
        if not resolved.get("success"):
            return _json(resolved)
        resolved_video_id = resolved["video"]["id"]

    result = await _call_vidgo_api(ctx, "GET", "/api/tasks/subtitle_generate/status")
    if resolved_video_id is None or not result.get("success"):
        return _json(result)

    key = str(resolved_video_id)
    return _json(
        {
            "success": True,
            "http_status": result.get("http_status"),
            "video_id": resolved_video_id,
            "task": result.get(key),
            "found": key in result,
        }
    )


@mcp.tool()
async def retry_subtitle_task(video_id: int, ctx: Context | None = None) -> str:
    """Retry a subtitle generation or translation task by video_id."""
    path = f"/api/tasks/subtitle_generate/{int(video_id)}/retry"
    return _json(await _call_vidgo_api(ctx, "POST", path))


@mcp.tool()
async def delete_subtitle_task(video_id: int, ctx: Context | None = None) -> str:
    """Delete a subtitle generation or translation task by video_id."""
    path = f"/api/tasks/subtitle_generate/{int(video_id)}/delete"
    return _json(await _call_vidgo_api(ctx, "POST", path))


@mcp.tool()
async def get_transcription_status(ctx: Context | None = None) -> str:
    """Return active transcription engine, availability, models, and downloads.

    Sensitive config values are redacted to booleans.
    """
    config = await _call_vidgo_api(ctx, "GET", "/api/config/")
    engines = await _call_vidgo_api(ctx, "GET", "/api/transcription-engines/")
    models = await _call_vidgo_api(ctx, "GET", "/api/vidunder-models/")
    progress = await _call_vidgo_api(ctx, "GET", "/api/vidunder-models/progress/")

    settings_data = config.get("data", {}) if config.get("success") else {}
    transcription = settings_data.get("Transcription Engine", {})
    active_engine = transcription.get("primary_engine")

    model_rows = []
    for item in models.get("data", {}).get("models", []):
        model_rows.append(
            {
                "name": item.get("name"),
                "label": item.get("label"),
                "status": item.get("status"),
                "downloaded_size": item.get("downloaded_size"),
                "total_size": item.get("total_size"),
            }
        )

    return _json(
        {
            "success": all(
                part.get("success") for part in [config, engines, models, progress]
            ),
            "active_engine": active_engine,
            "transcription_engine": _redact_settings(transcription),
            "available_engines": engines.get("data", {}).get("available_engines", []),
            "engines": engines.get("data", {}).get("engines", {}),
            "models": model_rows,
            "active_downloads": progress.get("progress", {}),
        }
    )


@mcp.tool()
async def list_model_status(ctx: Context | None = None) -> str:
    """List local VidGo model groups and their download status."""
    return _json(await _call_vidgo_api(ctx, "GET", "/api/vidunder-models/"))


@mcp.tool()
async def start_model_download(
    model_name: str,
    source: str = "hf",
    force: bool = False,
    ctx: Context | None = None,
) -> str:
    """Start downloading a local model group.

    Args:
        model_name: fun-asr, glm-asr, minicpm-v4.5, glm-ocr, or embedding.
        source: hf, ms, or modelscope.
        force: Re-download even if files already appear complete.
    """
    normalized_model = _normalize_model_name(model_name)
    normalized_source = (source or "hf").strip().lower()
    if normalized_source == "modelscope":
        normalized_source = "ms"
    if normalized_source not in {"hf", "ms"}:
        return _json({"success": False, "error": "source must be hf or modelscope"})
    return _json(
        await _call_vidgo_api(
            ctx,
            "POST",
            "/api/vidunder-models/download/",
            {
                "model_name": normalized_model,
                "source": normalized_source,
                "force": force,
            },
        )
    )


@mcp.tool()
async def get_model_download_progress(ctx: Context | None = None) -> str:
    """Get active local model download progress."""
    return _json(await _call_vidgo_api(ctx, "GET", "/api/vidunder-models/progress/"))


@mcp.tool()
async def cancel_model_download(
    model_name: str,
    ctx: Context | None = None,
) -> str:
    """Cancel a currently downloading local model group."""
    normalized_model = _normalize_model_name(model_name)
    return _json(
        await _call_vidgo_api(
            ctx,
            "DELETE",
            "/api/vidunder-models/download/",
            {"model_name": normalized_model},
        )
    )


@mcp.tool()
async def get_bilibili_sessdata_status(ctx: Context | None = None) -> str:
    """Return sanitized Bilibili SESSDATA status without exposing the cookie."""
    return _json(
        await _call_vidgo_api(
            ctx,
            "GET",
            "/api/media-credentials/bilibili-sessdata/",
        )
    )


@mcp.tool()
async def validate_bilibili_sessdata(ctx: Context | None = None) -> str:
    """Validate configured Bilibili SESSDATA and return username/UID if valid.

    The response is sanitized and never includes the cookie value.
    """
    return _json(
        await _call_vidgo_api(
            ctx,
            "GET",
            "/api/media-credentials/bilibili-sessdata/?validate=1",
            timeout=20,
        )
    )


@mcp.tool()
async def set_bilibili_sessdata(
    sessdata: str,
    ctx: Context | None = None,
) -> str:
    """Set server-side Bilibili SESSDATA.

    The response is sanitized and does not echo the cookie value.
    """
    if not sessdata.strip():
        return _json({"success": False, "error": "sessdata is required"})
    return _json(
        await _call_vidgo_api(
            ctx,
            "POST",
            "/api/media-credentials/bilibili-sessdata/",
            {"sessdata": sessdata},
        )
    )


@mcp.tool()
async def clear_bilibili_sessdata(ctx: Context | None = None) -> str:
    """Clear server-side Bilibili SESSDATA."""
    return _json(
        await _call_vidgo_api(
            ctx,
            "DELETE",
            "/api/media-credentials/bilibili-sessdata/",
        )
    )


def streamable_http_app():
    """Return the Streamable HTTP ASGI app."""
    return mcp.streamable_http_app()


def sse_app():
    """Return the legacy SSE ASGI app."""
    return mcp.sse_app()
