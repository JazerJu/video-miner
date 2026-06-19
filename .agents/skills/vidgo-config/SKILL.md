---
name: vidgo-config
description: Manage VidGo server-side settings through the backend config API. Use when the user asks to check or update Bilibili SESSDATA, Bilibili media credentials, download proxy settings, or other VidGo config values that live on the server rather than in the agent-side env.
---

# VidGo Config

Manage VidGo server-side configuration through `/api/config/`.

## Scope

Use this skill for settings stored by the VidGo backend, especially:

- Bilibili `SESSDATA`
- media credential status
- Bilibili/download proxy settings

Do not use this skill for agent-side API client settings such as `VIDGO_API_BASE` or `VIDGO_API_TOKEN`; use `vidgo-endpoint` for those.

## Safety Rules

- Never store real `SESSDATA` in `SKILL.md`, `Skills.md`, or other tracked docs.
- Never print the full `SESSDATA` value.
- Report only whether it is set, approximate length, and parsed expiration time if available.
- Prefer dedicated config endpoints over full `/api/config/` reads.
- The Bilibili SESSDATA endpoint returns sanitized status only; it never returns the cookie value.

## Prerequisites

Load agent-side API config first:

```bash
VIDGO_REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
source "$VIDGO_REPO_ROOT/.agents/skills/vidgo-endpoint/scripts/load_vidgo_env.sh"
vidgo_require_env
```

## Check Bilibili SESSDATA Status

```bash
python3 "$VIDGO_REPO_ROOT/.agents/skills/vidgo-config/scripts/bilibili_sessdata.py" status
```

Expected output does not include the cookie value:

```json
{
  "configured": true,
  "length": 220,
  "expires_at": "2026-12-04T12:34:56+00:00",
  "expired": false
}
```

## Set Bilibili SESSDATA

Pass the value directly to the dedicated API. Prefer stdin or a local secret file when avoiding shell history.

From stdin:

```bash
printf '%s' '<cookie-value-or-full-cookie-header>' |
python3 "$VIDGO_REPO_ROOT/.agents/skills/vidgo-config/scripts/bilibili_sessdata.py" set --stdin
```

From a local file:

```bash
python3 "$VIDGO_REPO_ROOT/.agents/skills/vidgo-config/scripts/bilibili_sessdata.py" set \
  --from-file "$HOME/.bilibili-sessdata"
```

Inline value when the user explicitly provides it in the current request:

```bash
python3 "$VIDGO_REPO_ROOT/.agents/skills/vidgo-config/scripts/bilibili_sessdata.py" set \
  --value '<cookie-value-or-full-cookie-header>'
```

After setting, run `status` to confirm the backend has a configured value.

## Clear Bilibili SESSDATA

Only clear it when the user explicitly asks to remove or reset the cookie.

```bash
python3 "$VIDGO_REPO_ROOT/.agents/skills/vidgo-config/scripts/bilibili_sessdata.py" clear
```

## Relationship to Downloads

Bilibili downloads read `Media Credentials.bilibili_sessdata` from the server config. If Bilibili query/download fails because login is required, the video is restricted, or 1080p+ streams are unavailable, ask the user for a fresh `SESSDATA` and set it with this skill before retrying `download-video`.

For Docker or remote deployments, this still works through the VidGo HTTP API. The skill does not read or edit the container's internal `config.ini` directly.

The VidGo frontend can still set the same value from the Settings page, under the media credentials section. The dedicated API is an additional lightweight path for agents and scripts, not a replacement for the UI.

## API Contract

- `GET /api/media-credentials/bilibili-sessdata/` returns sanitized status.
- `POST /api/media-credentials/bilibili-sessdata/` with `{"sessdata": "<value>"}` sets the server-side value.
- `DELETE /api/media-credentials/bilibili-sessdata/` clears the value.

The POST body may be either the raw `SESSDATA` value or a full Cookie header containing `SESSDATA=...`.
