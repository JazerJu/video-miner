# VidGo MCP

VidGo exposes an optional remote MCP endpoint for agents such as OpenCode or Pi Agent.
The main VidGo web/API service can keep running through WSGI; enabling MCP starts a
small ASGI process in the same container or backend environment.

## Endpoints

- `http://<host>:<VIDGO_MCP_PORT>/mcp` - Streamable HTTP transport.
- `http://<host>:<VIDGO_MCP_PORT>/sse` - legacy SSE transport compatibility.
- `http://<host>:<VIDGO_MCP_PORT>/health` - unauthenticated health check.

Use the same VidGo API token as normal API calls:

```jsonc
{
  "mcp": {
    "vidgo": {
      "type": "remote",
      "url": "http://192.168.1.20:8787/mcp",
      "headers": {
        "Authorization": "Bearer <VidGo API Token>"
      },
      "enabled": true
    }
  }
}
```

For clients that only support SSE-style URLs:

```jsonc
{
  "mcp": {
    "vidgo": {
      "type": "remote",
      "url": "http://192.168.1.20:8787/sse",
      "headers": {
        "Authorization": "Bearer <VidGo API Token>"
      },
      "enabled": true
    }
  }
}
```

## Docker

Set these variables in `.env`:

```env
ENABLE_MCP=1
VIDGO_MCP_PORT=8787
MCP_PORT=8787
VIDGO_MCP_PUBLIC_URL=http://192.168.1.20:8787
VIDGO_MCP_ALLOWED_HOSTS=localhost:*,127.0.0.1:*,192.168.1.20:*
VIDGO_MCP_ALLOWED_ORIGINS=http://localhost:*,http://127.0.0.1:*
```

`VIDGO_MCP_PORT` is the host port exposed to agents. `MCP_PORT` is the port inside
the container.

## Local Source Run

The default backend process still starts with WSGI:

```bash
cd backend
bash run_all.sh
```

Enable the optional MCP process:

```bash
cd backend
ENABLE_MCP=1 MCP_PORT=8787 bash run_all.sh
```

## Initial Tool Set

The first MCP version exposes a small pilot set:

- `test_connection`
- `list_videos`
- `search_videos`
- `get_video_info`

Later tools should be migrated from `.agents/skills/*/SKILL.md`, with skills kept
as fallback documentation for agents that do not support MCP.
