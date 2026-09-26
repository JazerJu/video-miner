"""Native subtitles and chapters of a downloaded video, used instead of local ASR.

YouTube tracks come from yt-dlp metadata, Bilibili tracks from the web player API; both
end up in the same stored shape. See the Bilibili section below for how its tracks are
chosen. On YouTube:

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


# ----------------------------------------------------------------- Bilibili

# Bilibili subtitle language tags. vidgo_lang() cannot read these: it splits on "-" and
# would take "ai-zh" for a language called "ai".
_BILI_ZH_TAGS = {"zh", "zh-hans", "zh-cn", "ai-zh"}

_KANA_RE = re.compile(r"[\u3040-\u30ff]")
_HANGUL_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff]")
_HAN_RE = re.compile(r"[\u4e00-\u9fff]")


def _bili_kind(track: dict) -> str:
    """How the track was made: by the uploader, by ASR, or by machine translation."""
    if track.get("type") == 0:
        return "bili-manual"
    return "bili-ai-translated" if track.get("ai_type") == 1 else "bili-ai"


def pick_bili_track(subtitle: dict | None) -> dict | None:
    """The Chinese subtitle track of a Bilibili part, or None.

    Only Chinese is taken, so a video that gets a track has raw_lang "zh" by construction
    and nothing has to stamp a language afterwards. Preference: the uploader track (type 0),
    then the AI track of the spoken language (ai_type 0), then the AI track translated into
    Chinese (ai_type 1). ai_type only ranks and never rejects: a video with non-Chinese
    audio usually carries the translated Chinese track and no source-language track at all,
    and that translation still beats running Chinese ASR over foreign speech.
    """
    tracks = [
        t
        for t in (subtitle or {}).get("subtitles") or []
        if str(t.get("lan") or "").lower() in _BILI_ZH_TAGS
        and (t.get("subtitle_url") or t.get("subtitle_url_v2"))
    ]
    if not tracks:
        return None
    return min(tracks, key=lambda t: (t.get("type", 1), t.get("ai_type", 1)))


def parse_bili_json(body: list) -> list[list]:
    """Cues of a Bilibili subtitle file as [start, end, text] lists.

    The file is {"body": [{"from": seconds, "to": seconds, "content": "..."}]}. They are
    already sentences, so there are no word-level cues to return alongside them.
    """
    cues = []
    for item in body or []:
        text = str(item.get("content") or "").strip()
        if not text:
            continue
        try:
            cues.append([float(item["from"]), float(item["to"]), text])
        except (KeyError, TypeError, ValueError):
            continue
    return _clamp(cues)


def looks_chinese(text: str) -> bool:
    """Whether the text of a track tagged Chinese really is Chinese.

    The lan tag is metadata, and a wrong one would label foreign text as the video's own
    transcript, which is worse than having no subtitle at all: ASR is skipped and the
    translation step believes the text is already Chinese. Measured over the subtitle files
    of the sampled videos, a Chinese track holds no kana at all, a Japanese one is 0.73 kana
    even though 0.20 of it is Han, and the Latin-script and Arabic ones hold no Han. The Han
    floor stays low because Chinese technical subtitles carry many English terms: the lowest
    Chinese sample seen was 0.75 Han.
    """
    if len(text) < 20:  # too short to measure; the lan tag is all there is
        return True
    n = len(text)
    if len(_KANA_RE.findall(text)) / n > 0.02 or len(_HANGUL_RE.findall(text)) / n > 0.02:
        return False
    return len(_HAN_RE.findall(text)) / n >= 0.30


def fetch_bili(subtitle: dict | None, get_body) -> dict | None:
    """Download and parse the Chinese track of a Bilibili part, or None.

    ``get_body`` fetches one subtitle url and returns its cue list. It lives in
    bili_download because it needs the Bilibili Referer and the configured proxy, and it is
    called right away because the url carries an auth_key that expires.
    """
    track = pick_bili_track(subtitle)
    if not track:
        return None
    segments = parse_bili_json(get_body(track.get("subtitle_url") or track.get("subtitle_url_v2")))
    if not segments or not looks_chinese("".join(text for _, _, text in segments)):
        return None
    return {
        "kind": _bili_kind(track),
        "tag": track.get("lan"),
        "lang": "zh",
        "segments": segments,
        "words": [],
    }


def _chapter_nodes(points, id_prefix: str) -> list[dict]:
    """(start, title) pairs in the Video.chapters format used by the chapter panel."""
    out = []
    for start, title in points:
        try:
            start = float(start)
        except (TypeError, ValueError):
            continue
        n = len(out) + 1
        out.append({
            "id": f"{id_prefix}-{n}",
            "title": str(title or f"Chapter {n}").strip(),
            "startTime": round(start, 3),
            "children": [],
        })
    return out


def chapters_from_info(info: dict) -> list[dict]:
    """yt-dlp chapters (YouTube author chapters) in the Video.chapters format."""
    return _chapter_nodes(((ch.get("start_time"), ch.get("title")) for ch in info.get("chapters") or []), "yt")


def chapters_from_view_points(view_points: list) -> list[dict]:
    """Bilibili uploader chapters in the Video.chapters format.

    They come from data.view_points of /x/player/wbi/v2 (docs/video/player.md in
    bilibili-API-collect). Entries with type 2 are the chapters: {"from": s, "to": s, "content": title}.
    """
    points = [(p.get("from"), p.get("content")) for p in view_points or [] if isinstance(p, dict) and p.get("type") == 2]
    return _chapter_nodes(points, "bili")


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
