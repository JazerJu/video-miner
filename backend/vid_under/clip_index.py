# -*- coding: utf-8 -*-
"""find_clips 的片段索引。

每 10 秒一段，把该段字幕、屏幕文字（GLM-OCR 原文）和画面合编成一个 WeMM 向量，查询时按余弦排序。
为什么这样设计、每个参数的实测依据，见笔记「find_clips-片段检索工具设计」。
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time

import numpy as np

CLIP_SECS = 10
FPS = 2.0
# 有字幕时画面只负责版面轮廓：640 与 960 在 R@10 上打平，编码只要四成算力。
# 没字幕时画面要自己读屏幕字：960 在说话类、试错类查询上明显更好（0.31→0.48、0.27→0.53）。
WIDTH_WITH_SUBTITLES = 640
WIDTH_NO_SUBTITLES = 960
MODEL_ID = "WeMM-Embedding-4B-nf4"
SCREEN_TEXT_CHARS = 1200
SNIPPET_CHARS = 100


class NoSubtitlesError(RuntimeError):
    """没有可用字幕，且调用方没开 force_index。"""


def no_subtitles_payload(video_id) -> dict:
    """默认拒绝给无字幕视频建索引时返回给 Agent 的说明。"""
    return {
        "ok": False,
        "error": "no_subtitles",
        "message": (f"Video {video_id} has no subtitles, so no index was built. Without subtitles, "
                    "queries about what the speaker says match much worse "
                    "(measured MRR drops from 0.82 to 0.48)."),
        "hints": [
            f"Recommended: call start_subtitle_generation(video_id={video_id}) first, "
            "then resubmit once the subtitles are ready.",
            "If the video has no narration (a screen recording or demo), or you only need to find clips "
            "by what is on screen, resubmit with force_index=true to index screen text and frames only.",
        ],
    }


def index_paths(index_dir, video_id):
    base = os.path.join(str(index_dir), f"video_{video_id}_clips")
    return base + ".npy", base + ".meta.json"


def _fingerprint(path, content_hash=True):
    if not path or not os.path.exists(path):
        return None
    if not content_hash:
        st = os.stat(path)                     # 视频动辄几 GB，只看大小和修改时间
        return f"{st.st_size}:{int(st.st_mtime)}"
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def source_fingerprints(video_path, srt_path, structure_path) -> dict:
    return {
        "video": _fingerprint(video_path, content_hash=False),
        "subtitles": _fingerprint(srt_path),
        "screen_text": _fingerprint(structure_path),
    }


def load_subtitles(srt_path) -> list[dict]:
    if not srt_path or not os.path.exists(srt_path):
        return []
    from srt_utils import parse_srt
    try:
        return [e for e in parse_srt(srt_path) if str(e.get("text") or "").strip()]
    except Exception:
        return []


def _screen_events(structure_path) -> list[tuple[float, str]]:
    if not structure_path or not os.path.exists(structure_path):
        return []
    with open(structure_path, encoding="utf-8") as fh:
        st = json.load(fh)
    events = []
    # terminal_outputs 被大模型合并改写过，是转述不是原文，不进索引
    for key, field in (("slides", "ocr_text"), ("code_snapshots", "code")):
        for item in st.get(key) or []:
            text = " ".join(str(item.get(field) or "").split())
            if text:
                events.append((float(item.get("time") or 0), text))
    return events


def _probe_duration(video_path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", video_path],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def _cut_clips(video_path, width, workdir) -> list[str]:
    """先一次解码成 2fps 小图的全关键帧中间文件，再按 10 秒 copy 切段：切点精确，几乎不耗时。"""
    inter = os.path.join(workdir, "inter.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video_path,
                    "-vf", f"fps={FPS:g},scale={width}:-2", "-an", "-g", "1", "-threads", "3", inter],
                   check=True)
    segdir = os.path.join(workdir, "seg")
    os.makedirs(segdir, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", inter, "-c", "copy", "-f", "segment",
                    "-segment_time", str(CLIP_SECS), "-reset_timestamps", "1",
                    os.path.join(segdir, "seg_%05d.mp4")], check=True)
    os.remove(inter)
    return sorted(glob.glob(os.path.join(segdir, "seg_*.mp4")))


def _segment_texts(n, duration, subtitles, events, has_subtitles):
    """每段的文字输入和给 Agent 看的一句摘录。格式与实测时一致。"""
    docs, snippets = [], []
    for i in range(n):
        a, b = i * CLIP_SECS, min((i + 1) * CLIP_SECS, duration)
        spoken = " ".join(e["text"] for e in subtitles if e["start"] < b and e["end"] > a).strip()
        screen = " ".join(t for ts, t in events if a <= ts < b)[:SCREEN_TEXT_CHARS]
        if has_subtitles:
            doc = f"字幕：{spoken}" if spoken else "字幕：（无）"
            if screen:
                doc += f" 屏幕文字：{screen}"
        else:
            doc = f"屏幕文字：{screen}" if screen else ""
        docs.append(doc)
        snippets.append((spoken or screen)[:SNIPPET_CHARS])
    return docs, snippets


def build_clip_index(video_id, video_path, srt_path, structure_path, index_dir,
                     force_index=False, progress_cb=None) -> dict:
    subtitles = load_subtitles(srt_path)
    has_subtitles = bool(subtitles)
    if not has_subtitles and not force_index:
        raise NoSubtitlesError(no_subtitles_payload(video_id)["message"])

    width = WIDTH_WITH_SUBTITLES if has_subtitles else WIDTH_NO_SUBTITLES
    duration = _probe_duration(video_path)
    events = _screen_events(structure_path)
    from external_api import embed_items_wemm, wemm_release

    os.makedirs(index_dir, exist_ok=True)
    workdir = tempfile.mkdtemp(prefix=f"clipindex_{video_id}_")
    t0 = time.time()
    try:
        clips = _cut_clips(video_path, width, workdir)
        n = len(clips)
        if n == 0:
            raise RuntimeError("ffmpeg produced no clips")
        docs, snippets = _segment_texts(n, duration, subtitles, events, has_subtitles)
        vectors = []
        for i, (doc, clip) in enumerate(zip(docs, clips)):
            item = {"video": clip}
            if doc:
                item["text"] = doc
            vectors.append(embed_items_wemm([item], fps=FPS)[0])
            if progress_cb:
                progress_cb(i + 1, n)
        matrix = np.stack(vectors).astype(np.float32)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        wemm_release()          # 建完就让出显存，别和排在后面的转录、OCR、caption 抢卡

    meta = {
        "video_id": video_id,
        "model": MODEL_ID,
        "dim": int(matrix.shape[1]),
        "clip_secs": CLIP_SECS,
        "fps": FPS,
        "width": width,
        "index_quality": "full" if has_subtitles else "no_subtitles",
        "forced": bool(force_index and not has_subtitles),
        "n_segments": n,
        "segments": [[i * CLIP_SECS, round(min((i + 1) * CLIP_SECS, duration), 3)] for i in range(n)],
        "snippets": snippets,
        "segments_with_screen_text": sum(1 for d in docs if "屏幕文字：" in d),
        "sources": source_fingerprints(video_path, srt_path, structure_path),
        "build_seconds": round(time.time() - t0, 1),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    npy_path, meta_path = index_paths(index_dir, video_id)
    # 先写临时文件再改名，建到一半失败时不留下半张表
    np.save(npy_path + ".tmp.npy", matrix)
    os.replace(npy_path + ".tmp.npy", npy_path)
    with open(meta_path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False)
    os.replace(meta_path + ".tmp", meta_path)
    return meta


def index_status(video_id, index_dir, video_path=None, srt_path=None, structure_path=None) -> dict:
    npy_path, meta_path = index_paths(index_dir, video_id)
    if not (os.path.exists(npy_path) and os.path.exists(meta_path)):
        return {"state": "missing"}
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    current = source_fingerprints(video_path, srt_path, structure_path)
    stale = [k for k, v in current.items() if meta.get("sources", {}).get(k) != v]
    return {
        "state": "stale" if stale else "ready",
        "stale_sources": stale,
        "index_quality": meta.get("index_quality"),
        "n_segments": meta.get("n_segments"),
        "width": meta.get("width"),
        "built_at": meta.get("built_at"),
    }


def search_clip_index(video_id, index_dir, query, top_k=5) -> dict:
    npy_path, meta_path = index_paths(index_dir, video_id)
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    matrix = np.load(npy_path).astype(np.float32)
    from external_api import embed_items_wemm
    q = embed_items_wemm([{"text": query}])[0].astype(np.float32)
    if q.shape[0] != matrix.shape[1]:
        raise RuntimeError(f"query dim {q.shape[0]} != index dim {matrix.shape[1]}; rebuild the index")
    sims = matrix @ q                        # 两边都由服务端 L2 归一化过，内积即余弦
    top_k = max(1, min(int(top_k), len(sims)))
    order = np.argsort(-sims)[:top_k]
    return {
        "ok": True,
        "index_quality": meta.get("index_quality"),
        # 硬阈值分不开真假查询（AUC 0.69），只给相对分让 Agent 自己判断：越小越可能是视频里没有的内容
        "relevance_margin": round(float(sims.max() - np.median(sims)), 4),
        "clips": [{
            "start": meta["segments"][i][0],
            "end": meta["segments"][i][1],
            "score": round(float(sims[i]), 4),
            "snippet": meta["snippets"][i],
        } for i in order],
    }
