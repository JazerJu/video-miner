"""Optional ASGI entrypoint for VidGo's remote MCP server.

The main VidGo app can keep running through WSGI. This module is intended for a
small optional uvicorn process that exposes MCP on a separate port.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vid_go.settings")

import django
from asgiref.sync import sync_to_async
from django.db import close_old_connections

django.setup()

from rest_framework.authtoken.models import Token
from video.mcp_server import sse_app, streamable_http_app


AsgiReceive = Callable[[], Awaitable[dict]]
AsgiSend = Callable[[dict], Awaitable[None]]
AsgiApp = Callable[[dict, AsgiReceive, AsgiSend], Awaitable[None]]


def _header(scope: dict, name: bytes) -> str:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin1")
    return ""


async def _send_text(send: AsgiSend, status: int, body: str) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body.encode("utf-8")})


@sync_to_async(thread_sensitive=True)
def _token_is_valid(token_key: str) -> bool:
    close_old_connections()
    try:
        return Token.objects.filter(key=token_key).exists()
    finally:
        close_old_connections()


class VidGoBearerAuthMiddleware:
    """Require an existing VidGo DRF API token for all MCP HTTP requests."""

    def __init__(self, app: AsgiApp):
        self.app = app

    async def __call__(self, scope: dict, receive: AsgiReceive, send: AsgiSend) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        if scope.get("path") == "/health":
            await self.app(scope, receive, send)
            return

        authorization = _header(scope, b"authorization")
        if not authorization.startswith("Bearer "):
            await _send_text(send, 401, "Missing Bearer token")
            return

        token_key = authorization[7:].strip()
        if not token_key or not await _token_is_valid(token_key):
            await _send_text(send, 403, "Invalid Bearer token")
            return

        await self.app(scope, receive, send)


class McpPathRouter:
    """Route Streamable HTTP and legacy SSE MCP paths to the SDK apps."""

    def __init__(self):
        self.streamable_app = streamable_http_app()
        self.sse_app = sse_app()

    async def __call__(self, scope: dict, receive: AsgiReceive, send: AsgiSend) -> None:
        path = scope.get("path", "")
        if path == "/health":
            await _send_text(send, 200, "ok")
            return
        if path.startswith("/sse") or path.startswith("/messages"):
            await self.sse_app(scope, receive, send)
            return
        await self.streamable_app(scope, receive, send)


application = VidGoBearerAuthMiddleware(McpPathRouter())
