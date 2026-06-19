#!/usr/bin/env bash

# Source this file, then call `vidgo_load_env`.
# It loads VidGo API client configuration for agent-side skill execution.

vidgo_find_repo_root() {
  git rev-parse --show-toplevel 2>/dev/null || pwd
}

vidgo_source_env_file() {
  local file="$1"
  [ -f "$file" ] || return 0

  local old_base="${VIDGO_API_BASE-}"
  local old_token="${VIDGO_API_TOKEN-}"

  set -a
  # shellcheck disable=SC1090
  source "$file"
  set +a

  [ -n "$old_base" ] && VIDGO_API_BASE="$old_base"
  [ -n "$old_token" ] && VIDGO_API_TOKEN="$old_token"
}

vidgo_load_env() {
  local repo_root="${VIDGO_REPO_ROOT:-$(vidgo_find_repo_root)}"
  local xdg_config="${XDG_CONFIG_HOME:-$HOME/.config}"
  local candidates=()

  [ -n "${VIDGO_AGENT_ENV:-}" ] && candidates+=("$VIDGO_AGENT_ENV")
  candidates+=(
    "$xdg_config/vidgo/agent.env"
    "$HOME/.vidgo-agent.env"
    "$repo_root/.vidgo-agent.env"
    "$repo_root/.env"
  )

  local file
  for file in "${candidates[@]}"; do
    if [ -z "${VIDGO_API_BASE:-}" ] || [ -z "${VIDGO_API_TOKEN:-}" ]; then
      vidgo_source_env_file "$file"
    fi
  done

  if [ -n "${VIDGO_API_BASE:-}" ]; then
    case "$VIDGO_API_BASE" in
      http://*|https://*) ;;
      *) VIDGO_API_BASE="http://$VIDGO_API_BASE" ;;
    esac
    VIDGO_API_BASE="${VIDGO_API_BASE%/}"
  fi

  export VIDGO_API_BASE VIDGO_API_TOKEN
}

vidgo_require_env() {
  vidgo_load_env

  local missing=()
  [ -z "${VIDGO_API_BASE:-}" ] && missing+=("VIDGO_API_BASE")
  [ -z "${VIDGO_API_TOKEN:-}" ] && missing+=("VIDGO_API_TOKEN")

  if [ "${#missing[@]}" -gt 0 ]; then
    printf 'Missing VidGo agent config: %s\n' "${missing[*]}" >&2
    printf 'Set them in the process environment, $VIDGO_AGENT_ENV, ~/.config/vidgo/agent.env, ~/.vidgo-agent.env, or repo .env.\n' >&2
    return 2
  fi
}

vidgo_env_status() {
  vidgo_load_env
  printf 'VIDGO_API_BASE=%s\n' "${VIDGO_API_BASE:-unset}"
  if [ -n "${VIDGO_API_TOKEN:-}" ]; then
    printf 'VIDGO_API_TOKEN=set\n'
  else
    printf 'VIDGO_API_TOKEN=unset\n'
  fi
}
