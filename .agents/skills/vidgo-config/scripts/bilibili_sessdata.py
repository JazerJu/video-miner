#!/usr/bin/env python3
"""Manage VidGo Bilibili SESSDATA through the dedicated backend API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _api_base() -> str:
    base = _env("VIDGO_API_BASE")
    if not base:
        raise SystemExit("VIDGO_API_BASE is not set")
    if not base.startswith(("http://", "https://")):
        base = "http://" + base
    return base.rstrip("/")


def _token() -> str:
    token = _env("VIDGO_API_TOKEN")
    if not token:
        raise SystemExit("VIDGO_API_TOKEN is not set")
    return token


def _request(method: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
    }
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        _api_base() + "/api/media-credentials/bilibili-sessdata/",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Connection error: {exc.reason}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit("Backend returned non-JSON response") from exc


def _read_new_value(args: argparse.Namespace) -> str:
    if args.stdin:
        value = sys.stdin.read()
    elif args.from_file:
        value = Path(args.from_file).read_text(encoding="utf-8")
    elif args.value:
        value = args.value
    else:
        raise SystemExit("No SESSDATA provided. Use --value, --from-file, or --stdin.")

    value = value.strip()
    if not value:
        raise SystemExit("SESSDATA value is empty")
    return value


def _print_sanitized(result: dict[str, Any]) -> None:
    if not result.get("success"):
        raise SystemExit(result.get("error") or "Request failed")
    print(json.dumps(result.get("data", {}), ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage VidGo Bilibili SESSDATA")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="Show sanitized SESSDATA status")
    set_parser = sub.add_parser("set", help="Set Bilibili SESSDATA")
    set_parser.add_argument("--value", help="Raw SESSDATA or full Cookie header")
    set_parser.add_argument("--from-file", help="Read SESSDATA from a local file")
    set_parser.add_argument("--stdin", action="store_true", help="Read SESSDATA from stdin")
    sub.add_parser("clear", help="Clear Bilibili SESSDATA")

    args = parser.parse_args()

    if args.cmd == "status":
        _print_sanitized(_request("GET"))
        return 0

    if args.cmd == "set":
        _print_sanitized(_request("POST", {"sessdata": _read_new_value(args)}))
        return 0

    if args.cmd == "clear":
        _print_sanitized(_request("DELETE"))
        return 0

    raise AssertionError(args.cmd)


if __name__ == "__main__":
    raise SystemExit(main())
