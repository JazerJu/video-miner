"""Native subtitles and chapters from yt-dlp metadata (YouTube).

A video that already has subtitles on YouTube does not need local ASR:

- Human-made subtitles in the original language are used as they are.
- Without them, the automatic captions of the original audio track are used. yt-dlp
  lists that track twice, as ``<lang>`` and ``<lang>-orig``. Their per-word timestamps
  give the same one-word-per-cue SRT that ASR writes in word mode, so the LLM sentence
  split runs on them unchanged.
- Machine-translated caption tracks are never used.

The chosen track is stored as ``MEDIA_ROOT/native_subtitles/<video_id>.json``. The
download task writes its sentence-level SRT as the video's subtitle, and the subtitle
task reads the JSON instead of running ASR when the language matches.
"""
from __future__ import annotations

import html
import json
import os
import re

# yt-dlp language tag prefix -> VidGo subtitle language code
_VIDGO_LANGS = {"en": "en", "zh": "zh", "ja": "jp", "de": "de"}

_TS = r"(?:(\d+):)?(\d{2}):(\d{2})\.(\d{3})"
_CUE_RE = re.compile(rf"^\s*{_TS}\s+-->\s+{_TS}")
_INLINE_SPLIT_RE = re.compile(r"<((?:\d+:)?\d{2}:\d{2}\.\d{3})>")
_TAG_RE = re.compile(r"<[^>]+>")


def vidgo_lang(tag: str | None) -> str | None:
    """Map a yt-dlp language tag (en-US, zh-Hans, ja, en-orig) to a VidGo code."""
    if not tag:
        return None
    return _VIDGO_LANGS.get(re.split(r"[-_]", str(tag).lower())[0])


def _seconds(h, m, s, ms) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def _inline_seconds(stamp: str) -> float:
    parts = stamp.split(":")
    if len(parts) == 2:
        parts.insert(0, "0")
    sec, ms = parts[2].split(".")
    return _seconds(parts[0], parts[1], sec, ms)


def pick_track(info: dict) -> dict | None:
    """Choose the subtitle track to use instead of ASR, or None.

    Returns {"kind": "manual"|"auto", "tag": yt-dlp tag, "lang": VidGo code, "formats": [...]}.
    """
    manual = {t: f for t, f in (info.get("subtitles") or {}).items() if f and vidgo_lang(t)}
    auto = info.get("automatic_captions") or {}
    orig_tags = [t for t in auto if t.endswith("-orig") and vidgo_lang(t)]
    original = vidgo_lang(info.get("language")) or (vidgo_lang(orig_tags[0]) if orig_tags else None)

    if manual:
        # Original language first, then the plain tag ("en" before "en-US").
        candidates = sorted(manual, key=lambda t: (vidgo_lang(t) != original, len(t), t))
        tag = candidates[0]
        if original is None or vidgo_lang(tag) == original:
            return {"kind": "manual", "tag": tag, "lang": vidgo_lang(tag), "formats": manual[tag]}

    if original:
        # Only the original-language ASR track. Without "-orig" a plain tag may be a translation,
        # so it is accepted only when yt-dlp reports the video language.
        tag = next((t for t in orig_tags if vidgo_lang(t) == original), None)
        if tag is None and info.get("language"):
            tag = next((t for t in auto if t.lower() == str(info["language"]).lower()), None)
        if tag and auto.get(tag):
            return {"kind": "auto", "tag": tag, "lang": original, "formats": auto[tag]}
    return None


def parse_vtt(text: str) -> tuple[list[list], list[list]]:
    """Parse WebVTT into (sentence-level cues, word-level cues) as [start, end, text] lists.

    Word-level cues exist only for YouTube automatic captions, whose new words carry inline
    timestamps. Their 10 ms transition cues and the carried-over first line of each cue repeat
    earlier text and are skipped.
    """
    cues = []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    while i < len(lines):
        m = _CUE_RE.match(lines[i])
        i += 1
        if not m:
            continue
        start, end = _seconds(*m.groups()[:4]), _seconds(*m.groups()[4:])
        body = []
        while i < len(lines) and lines[i] != "":
            # Automatic captions put a line holding one space above the first words of a cue,
            # so only a space line before a blank line or the next cue ends the cue.
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if not lines[i].strip() and (nxt == "" or _CUE_RE.match(nxt)):
                break
            body.append(lines[i])
            i += 1
        cues.append((start, end, body))

    is_auto = any(_INLINE_SPLIT_RE.search(line) for _, _, body in cues for line in body)
    segments, words = [], []
    for start, end, body in cues:
        if is_auto:
            for line in body:
                if not _INLINE_SPLIT_RE.search(line):
                    continue
                parts = _INLINE_SPLIT_RE.split(line)  # [word0, t1, word1, t2, word2, ...]
                stamps = [start] + [_inline_seconds(t) for t in parts[1::2]]
                tokens = [html.unescape(_TAG_RE.sub("", p)).strip() for p in parts[0::2]]
                line_words = [[t, w] for t, w in zip(stamps, tokens) if w]
                for k, (t, w) in enumerate(line_words):
                    w_end = line_words[k + 1][0] if k + 1 < len(line_words) else end
                    words.append([t, w_end, w])
                if line_words:
                    segments.append([start, end, " ".join(w for _, w in line_words)])
        else:
            content = " ".join(html.unescape(_TAG_RE.sub("", line)).strip() for line in body).strip()
            if not content:
                continue
            if segments and segments[-1][2] == content:
                segments[-1][1] = end
            else:
                segments.append([start, end, content])
    return _clamp(segments), _clamp(words)


def _clamp(items: list[list]) -> list[list]:
    """Sort by start and end each cue no later than the next one starts."""
    items.sort(key=lambda c: c[0])
    for cur, nxt in zip(items, items[1:]):
        if nxt[0] > cur[0]:
            cur[1] = min(cur[1], nxt[0])
        cur[1] = max(cur[1], cur[0] + 0.01)
    for c in items:
        c[0], c[1] = round(c[0], 3), round(max(c[1], c[0] + 0.01), 3)
    return items


def _fmt_srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(cues: list[list]) -> str:
    return "".join(
        f"{i}\n{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}\n{text}\n\n"
        for i, (start, end, text) in enumerate(cues, 1)
    )


def fetch(ydl, info: dict) -> dict | None:
    """Download and parse the track chosen by pick_track with an open YoutubeDL, or None."""
    track = pick_track(info)
    if not track:
        return None
    fmt = next((f for f in track["formats"] if f.get("ext") == "vtt"), None)
    if not fmt:
        return None
    raw = fmt.get("data")
    if raw is None:
        raw = ydl.urlopen(fmt["url"]).read().decode("utf-8", "replace")
    segments, words = parse_vtt(raw)
    if not segments:
        return None
    return {
        "kind": track["kind"],
        "tag": track["tag"],
        "lang": track["lang"],
        "segments": segments,
        "words": words,
    }


def chapters_from_info(info: dict) -> list[dict]:
    """yt-dlp chapters in the Video.chapters format used by the chapter panel."""
    out = []
    for i, ch in enumerate(info.get("chapters") or []):
        try:
            start = float(ch.get("start_time"))
        except (TypeError, ValueError):
            continue
        out.append({
            "id": f"yt-{i + 1}",
            "title": str(ch.get("title") or f"Chapter {i + 1}").strip(),
            "startTime": round(start, 3),
            "children": [],
        })
    return out


def _path(media_root: str, video_id) -> str:
    return os.path.join(media_root, "native_subtitles", f"{video_id}.json")


def save(media_root: str, video_id, native: dict) -> str:
    path = _path(media_root, video_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(native, f, ensure_ascii=False)
    return path


def load(media_root: str, video_id, lang: str) -> dict | None:
    """The stored native track for this video, if it is in ``lang``."""
    try:
        with open(_path(media_root, video_id), encoding="utf-8") as f:
            native = json.load(f)
    except (OSError, ValueError):
        return None
    return native if native.get("lang") == lang and native.get("segments") else None
