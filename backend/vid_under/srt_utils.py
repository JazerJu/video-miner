# coding=utf-8
"""SRT 字幕解析、搜索、与 timestamp 对齐."""

import re
from pathlib import Path


def parse_srt(srt_path: str | Path) -> list[dict]:
    blocks = Path(srt_path).read_text(encoding="utf-8").strip().split("\n\n")
    entries = []
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        m = re.match(r"(\d+):(\d+):(\d+)[.,](\d+)\s*-->\s*(\d+):(\d+):(\d+)[.,](\d+)", lines[1])
        if not m:
            continue
        start = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 1000
        end = int(m.group(5)) * 3600 + int(m.group(6)) * 60 + int(m.group(7)) + int(m.group(8)) / 1000
        text = " ".join(lines[2:]).strip()
        entries.append({"start": start, "end": end, "text": text})
    return entries


def transcript_for_timerange(entries: list[dict], start_s: float, end_s: float) -> str:
    lines = []
    for e in entries:
        if e["end"] <= start_s:
            continue
        if e["start"] >= end_s:
            break
        lines.append(f"[{_fmt(e['start'])}] {e['text']}")
    return "\n".join(lines)


def full_transcript(entries: list[dict]) -> str:
    return "\n".join(f"[{_fmt(e['start'])}] {e['text']}" for e in entries)


def search_transcript(entries: list[dict], query: str, top_k: int = 10) -> list[dict]:
    if any('\u4e00' <= c <= '\u9fff' for c in query):
        kw_list = []
        for i in range(0, len(query) - 1):
            kw_list.append(query[i:i+2])
        kw_list = list(set(kw_list))
    else:
        kw_list = query.lower().split()

    results = []
    for e in entries:
        tl = e["text"].lower()
        score = sum(tl.count(kw) for kw in kw_list)
        if score > 0:
            results.append({**e, "score": score})
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def _fmt(seconds: float) -> str:
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
