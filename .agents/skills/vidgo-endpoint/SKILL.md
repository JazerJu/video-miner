---
name: vidgo-endpoint
description: Configure, inspect, and test the VidGo backend API base URL for OpenCode or Pi agent workflows. Use when the user mentions changing host, domain, IP address, port, localhost, 127.0.0.1, remote backend access, connection failures, or asks which VidGo API endpoint the skills are using.
---

# VidGo Endpoint

Configure the VidGo API address used by every VidGo skill through `VIDGO_API_BASE`.

## Scope

Skills run where the agent runs. They cannot automatically read a remote server's filesystem, a remote Docker container's environment, or a container-internal `.env`.

Treat `VIDGO_API_BASE` and `VIDGO_API_TOKEN` as agent-side configuration:

- For local backend: use a local ignored env file such as `/media/jju/ExtraDisk/VidGo/.env`.
- For remote backend: store the public API URL and token in the agent-side env, or have the user provide them in the request.
- For local Docker backend: use the host-published port, not the container-internal port.
- For remote Docker backend: use the domain/IP and published host port, not the remote container `.env`.
- Only inspect Docker container env if the agent is on the same machine and the user explicitly asks; never print secrets.

Do not store real secrets directly in `SKILL.md`. Skills are shareable instructions. Store secrets in process environment variables or in an ignored agent-side env file.

## Supported Config Locations

`scripts/load_vidgo_env.sh` is the shared loader for VidGo skills. It checks these sources in order while preserving already-exported variables:

1. Existing process environment: `VIDGO_API_BASE`, `VIDGO_API_TOKEN`.
2. File pointed to by `VIDGO_AGENT_ENV`.
3. `$XDG_CONFIG_HOME/vidgo/agent.env` or `~/.config/vidgo/agent.env`.
4. `~/.vidgo-agent.env`.
5. Repo-local `.vidgo-agent.env`.
6. Repo-local `.env`.

Example agent-side env file:

```bash
VIDGO_API_BASE=https://your-vidgo-domain.com
VIDGO_API_TOKEN=<your-token>
```

Use `.agents/vidgo-agent.env.example` as the non-secret template.

## Address Rules

- Use `VIDGO_API_BASE` as the single source of truth for agent API calls.
- Accept full URLs such as `http://192.168.1.20:8080`, `http://localhost:8080`, or `https://video.example.com`.
- If the user gives `host:port` without a scheme, prepend `http://`.
- If the user gives only a port, keep the current scheme and host and replace only the port.
- Remove a trailing slash before storing or using the value.
- Do not hardcode `127.0.0.1:8080`; that is only a local default.
- Never print `VIDGO_API_TOKEN`.

## Load Current Configuration

Prefer already-exported environment variables. If they are missing, load a trusted agent-side env file.

```bash
VIDGO_REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
source "$VIDGO_REPO_ROOT/.agents/skills/vidgo-endpoint/scripts/load_vidgo_env.sh"
vidgo_env_status
```

If `VIDGO_API_BASE` is unset, default to `http://localhost:8080` only for the current command and tell the user it is a fallback.

## Normalize a User-Provided Address

```bash
USER_BASE='<USER_SUPPLIED_HOST_OR_URL>'
case "$USER_BASE" in
  http://*|https://*) VIDGO_API_BASE="$USER_BASE" ;;
  *) VIDGO_API_BASE="http://$USER_BASE" ;;
esac
VIDGO_API_BASE="${VIDGO_API_BASE%/}"
export VIDGO_API_BASE
printf 'Using VIDGO_API_BASE=%s\n' "$VIDGO_API_BASE"
```

Use the normalized value immediately for the requested workflow.

If the user gives only a port:

```bash
VIDGO_REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
source "$VIDGO_REPO_ROOT/.agents/skills/vidgo-endpoint/scripts/load_vidgo_env.sh"
vidgo_load_env
NEW_PORT='<PORT>'
VIDGO_API_BASE=$(python3 -c '
import os, sys
from urllib.parse import urlparse, urlunparse
base = os.environ.get("VIDGO_API_BASE") or "http://localhost:8080"
port = sys.argv[1]
p = urlparse(base if "://" in base else "http://" + base)
host = p.hostname or "localhost"
netloc = f"{host}:{port}"
print(urlunparse((p.scheme or "http", netloc, "", "", "", "")))
' "$NEW_PORT")
export VIDGO_API_BASE
printf 'Using VIDGO_API_BASE=%s\n' "$VIDGO_API_BASE"
```

## Test Connectivity

Use a small authenticated endpoint and report only the HTTP status and a concise interpretation.

```bash
VIDGO_REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
source "$VIDGO_REPO_ROOT/.agents/skills/vidgo-endpoint/scripts/load_vidgo_env.sh"
vidgo_require_env
VIDGO_API_BASE="${VIDGO_API_BASE%/}"

TMP=$(mktemp)
HTTP_CODE=$(curl -sS -m 8 -o "$TMP" -w '%{http_code}' \
  "$VIDGO_API_BASE/api/tags/" \
  -H "Authorization: Bearer $VIDGO_API_TOKEN")

case "$HTTP_CODE" in
  200) echo "VidGo API reachable and token accepted: $VIDGO_API_BASE" ;;
  401|403) echo "VidGo API reachable, but token was rejected: $HTTP_CODE" ;;
  000) echo "Cannot reach VidGo API at $VIDGO_API_BASE" ;;
  *) echo "VidGo API returned HTTP $HTTP_CODE at $VIDGO_API_BASE" ;;
esac
rm -f "$TMP"
```

If the user is only asking what address is configured, do not run broader workflows.

## Persist a New Address

Persist only when the user explicitly asks to save, remember, set permanently, or update `.env`.

Persist to an agent-side env file. Do not claim to update a remote server or Docker container `.env` unless the agent has explicit remote access and the user asked for that.

```bash
ENV_FILE="${VIDGO_AGENT_ENV:-$HOME/.vidgo-agent.env}"
NEW_BASE='<NORMALIZED_BASE_URL>'
NEW_BASE="${NEW_BASE%/}"
mkdir -p "$(dirname "$ENV_FILE")"
touch "$ENV_FILE"

NEW_BASE="$NEW_BASE" perl -0pi -e '
  if (/^VIDGO_API_BASE=/m) {
    s/^VIDGO_API_BASE=.*$/VIDGO_API_BASE=$ENV{NEW_BASE}/m;
  } else {
    $_ .= "\nVIDGO_API_BASE=$ENV{NEW_BASE}\n";
  }
' "$ENV_FILE"
```

After persisting, reload the agent-side env file and run the connectivity test.

## Docker Notes

Container env is server-side runtime configuration; it is not the agent's API client configuration.

- If Docker runs on the same machine and `docker-compose.yml` maps `8010:8000`, use `VIDGO_API_BASE=http://localhost:8010`.
- If Docker runs on another machine, use `http://<server-ip>:<published-port>` or the HTTPS reverse-proxy domain.
- If the agent itself runs inside the same Compose network, service DNS like `http://vidgo:8000` may work.
- Do not use `http://localhost:8000` from the agent just because the container exposes `8000`; from outside the container, `localhost` means the agent host.

## MCP Endpoint Notes

OpenCode remote MCP configuration is not a replacement for `VIDGO_API_BASE`. An MCP URL such as `http://127.0.0.1:8787/sse` only reaches the MCP transport. It may be localhost because of an SSH tunnel, while VidGo web/API/media files are served from another port such as `8080`.

- Keep `VIDGO_API_BASE` pointed at the VidGo web/API origin, for example `http://127.0.0.1:8080` for a local tunnel or `http://<server-ip>:8080` for direct remote access.
- Leave root-relative media paths returned in summaries unchanged by default. If the user explicitly asks for clickable media links, prefix paths such as `/media/vidunder/output/...` with the user-provided VidGo web/API base URL.
- For SSH tunnel testing with local OpenCode, forward both ports when using localhost addresses: `-L 8787:127.0.0.1:8787 -L 8080:127.0.0.1:8080`.

## Backend Host Notes

- The backend default port is controlled by `PORT`; `backend/run_all.sh` defaults to `8080`.
- The backend binds to `0.0.0.0:$PORT`, so LAN IP access can work when the OS firewall and network allow it.
- For browser access from another origin, configure `VIDGO_URL`, `VIDGO_CORS_ALLOWED_ORIGINS`, and `VIDGO_CSRF_TRUSTED_ORIGINS` if needed.
- For agent `curl` calls with bearer token, the main requirements are network reachability, correct `VIDGO_API_BASE`, and a valid `VIDGO_API_TOKEN`.

## Response Guidance

- If the endpoint works, answer with the active base URL and what was tested.
- If it fails, distinguish address/network failure from token failure.
- If the user gives an IP/domain as part of another VidGo task, normalize and test it first, then continue with the requested workflow.
- Do not expose secrets from `.env`.
