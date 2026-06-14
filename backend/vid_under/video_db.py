# coding=utf-8
"""离线：分段 → 抽帧 → MiniCPM-V caption → 存数据库."""
import sys
import json
import time
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import minicpmv_llama
from preprocess import preprocess_frame, extract_frames
from config import EXPORT_DIR, GGUF_PATH


def _get_video_fps(video_path: str) -> float:
    import subprocess, json
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-select_streams", "v:0", "-show_streams", video_path], capture_output=True, text=True)
    info = json.loads(r.stdout)
    stream = info["streams"][0]
    fps_str = stream.get("r_frame_rate", "30/1")
    num, den = fps_str.split("/")
    return float(num) / float(den) if float(den) else 30.0



def _preprocess_frames(frames, max_slice_nums=1):
    tiles, meta = [], []
    for fi, frame in enumerate(frames):
        frame_tiles = preprocess_frame(frame, frame_idx=fi, version="4.5", max_slice_nums=max_slice_nums)
        for j, tile in enumerate(frame_tiles):
            tiles.append(tile)
            meta.append({"frame": fi, "tile": j, "h": tile["h"], "w": tile["w"]})
    return tiles, meta

from config import (
    DB_DIR, CLIP_SECS, VIDEO_FPS, FRAMES_PER_CLIP,
    MAX_SLICE_NUMS, GGUF_PATH, EXPORT_DIR,
    N_CTX, N_GPU_LAYERS, N_BATCH, N_PREDICT, KV_CACHE_TYPE,
    TOKENS_DIR,
)
from srt_utils import parse_srt, transcript_for_timerange


def build_database(video_path: str, srt_path: str, db_name: str = "default",
                   clip_secs: int = None, video_fps: float = None,
                   frames_per_clip: int = None,
                   progress_cb=None) -> dict:
    clip_secs = clip_secs or CLIP_SECS
    video_fps = video_fps or VIDEO_FPS
    frames_per_clip = frames_per_clip or FRAMES_PER_CLIP

    DB_DIR.mkdir(parents=True, exist_ok=True)
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)

    srt_entries = parse_srt(srt_path)
    duration = _get_duration(video_path)
    n_clips = int(np.ceil(duration / clip_secs))

    model, ctx, sampler = _load_llm()
    siglip_sess, resampler_sess = _load_onnx()

    clips = []
    for i in range(n_clips):
        start, end = i * clip_secs, min((i + 1) * clip_secs, duration)
        if end - start < 2:
            continue

        t0 = time.time()
        frames = _extract_clip_frames(video_path, start, end, video_fps, frames_per_clip)
        transcript = transcript_for_timerange(srt_entries, start, end)

        caption, vis = _caption_frames(
            frames, transcript, model, ctx, sampler,
            siglip_sess, resampler_sess,
        )

        dense_path = str(TOKENS_DIR / f"{db_name}_dense_{i:04d}.npy")
        np.save(dense_path, vis.astype(np.float32))

        clips.append({
            "idx": i, "start": start, "end": end,
            "caption": caption, "frames_extracted": len(frames),
            "has_transcript": len(transcript) > 0,
            "dense_tokens": dense_path,
            "n_dense_tokens": int(vis.shape[0]),
        })

        elapsed = time.time() - t0
        if (i + 1) % 10 == 0:
            print(f"  [{i+1}/{n_clips}] {elapsed:.0f}s/clip  ({start:.0f}s-{end:.0f}s)")
        if progress_cb:
            progress_cb("caption", i + 1, n_clips)

    ctx.clear_kv()
    db = {"video_path": str(video_path), "duration": duration,
          "srt_path": str(srt_path), "n_clips": n_clips,
          "clip_secs": clip_secs, "video_fps": video_fps,
          "frames_per_clip": frames_per_clip,
          "clips": clips,
          "full_transcript": _full_transcript_text(srt_entries)}

    db_path = DB_DIR / f"{db_name}.json"
    db_path.write_text(json.dumps(db, ensure_ascii=False, indent=2))
    print(f"\n数据库已保存: {db_path}  ({len(clips)} clips)")
    return db


def _get_duration(path: str) -> float:
    import subprocess, json
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
        capture_output=True, text=True, check=True)
    return float(json.loads(r.stdout)["format"]["duration"])


def _extract_clip_frames(video_path: str, start: float, end: float,
                         video_fps: float = None, frames_per_clip: int = None) -> list:
    import subprocess, os
    from PIL import Image
    video_fps = video_fps or VIDEO_FPS
    frames_per_clip = frames_per_clip or FRAMES_PER_CLIP
    clip_duration = end - start

    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name,width,height", "-of", "csv=p=0", video_path],
        capture_output=True, text=True, check=True)
    codec, width, height = probe.stdout.strip().split(",")
    width, height = int(width), int(height)

    hwaccel = os.environ.get("VIDUNDER_HWACCEL", "none")
    if hwaccel == "cuda":
        hwaccel_args = ["-c:v", f"{codec}_cuvid"]
    elif hwaccel == "vaapi":
        hwaccel_args = ["-hwaccel", "vaapi"]
    else:
        hwaccel_args = []

    cmd = ["ffmpeg", "-y"] + hwaccel_args + [
        "-ss", str(start), "-t", str(clip_duration),
        "-i", video_path,
        "-vf", f"fps={video_fps}",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-v", "quiet", "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError:
        cmd_fallback = ["ffmpeg", "-y",
                        "-ss", str(start), "-t", str(clip_duration),
                        "-i", video_path,
                        "-vf", f"fps={video_fps}",
                        "-f", "rawvideo", "-pix_fmt", "rgb24",
                        "-v", "quiet", "-"]
        proc = subprocess.run(cmd_fallback, capture_output=True, check=True)
    raw = proc.stdout

    frame_size = width * height * 3
    frames = [Image.frombytes("RGB", (width, height), raw[i:i + frame_size])
              for i in range(0, len(raw), frame_size)
              if i + frame_size <= len(raw)]
    if len(frames) > frames_per_clip:
        indices = np.linspace(0, len(frames) - 1, frames_per_clip, dtype=int)
        frames = [frames[i] for i in indices]
    return frames


def _load_llm():
    model = minicpmv_llama.LlamaModel(str(GGUF_PATH), n_gpu_layers=N_GPU_LAYERS)
    kv_type = {"q4_0": 2, "q8_0": 8, "fp16": 1}.get(KV_CACHE_TYPE, 0)
    ctx = minicpmv_llama.LlamaContext(model, n_ctx=N_CTX, n_batch=N_BATCH, n_ubatch=N_BATCH, cache_type_k=kv_type, cache_type_v=kv_type)
    sampler = minicpmv_llama.LlamaSampler(temperature=0, repeat_penalty=1.1)
    return model, ctx, sampler


def _load_onnx():
    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    siglip = ort.InferenceSession(str(Path(EXPORT_DIR) / "minicpmv_v45_siglip.fp32.onnx"), sess_options=opts, providers=providers)
    resampler = ort.InferenceSession(str(Path(EXPORT_DIR) / "minicpmv_v45_resampler_temporal.fp16.onnx"), sess_options=opts, providers=providers)
    return siglip, resampler


def _compute_onnx_inputs_v45(h, w, npps=70, resampler_embed_dim=4096):
    from preprocess import get_2d_sincos_pos_embed_numpy
    bucket_h = np.clip((np.arange(h) * npps) // h, 0, npps - 1)
    bucket_w = np.clip((np.arange(w) * npps) // w, 0, npps - 1)
    pos_ids = (bucket_h[:, None] * npps + bucket_w).flatten().astype(np.int64)
    spatial_pos_embed = get_2d_sincos_pos_embed_numpy(resampler_embed_dim, (h, w))
    spatial_pos_embed = spatial_pos_embed.reshape(h * w, -1).astype(np.float32)
    return {"pos_ids": pos_ids, "spatial_pos_embed": spatial_pos_embed}



def _caption_frames(frames, transcript, model, ctx, sampler, siglip_sess, resampler_sess):
    from config import NPPS, EMBED_DIM, VIDEO_PATH as _VIDEO
    if not frames:
        return "(无画面)", np.empty((0, EMBED_DIM), dtype=np.float32)

    tiles, meta = _preprocess_frames(frames, max_slice_nums=MAX_SLICE_NUMS)
    vid_fps = _get_video_fps(str(_VIDEO))

    siglip_features, patch_counts = [], []
    for tile in tiles:
        h, w = tile["h"], tile["w"]
        inputs = _compute_onnx_inputs_v45(h, w, NPPS)
        pv = tile["pixel_values"].astype(np.float32)
        feat = siglip_sess.run(["siglip_features"], {"pixel_values": pv, "pos_ids": inputs["pos_ids"]})[0]
        siglip_features.append(feat)
        patch_counts.append(h * w)

    from preprocess import (
        get_2d_sincos_pos_embed_numpy, encode_video_temporal_ids,
        compute_temporal_embeddings_for_group,
    )
    total = len(frames)
    tids = encode_video_temporal_ids(np.linspace(0, total - 1, total, dtype=int), vid_fps)

    gf = np.concatenate(siglip_features, axis=0)
    sp = np.concatenate([get_2d_sincos_pos_embed_numpy(EMBED_DIM, (tiles[i]["h"], tiles[i]["w"])).reshape(tiles[i]["h"] * tiles[i]["w"], -1) for i in range(len(tiles))], axis=0)
    te = compute_temporal_embeddings_for_group(patch_counts, tids, EMBED_DIM)
    vt = resampler_sess.run(None, {
        "siglip_features": gf.astype(np.float16),
        "spatial_pos_embeds": sp.astype(np.float16),
        "temporal_pos_embeds": te.astype(np.float16),
    })[0]
    vis = vt.astype(np.float32)
    ctx.clear_kv()

    transcript_hint = f"\n该时间段字幕:\n{transcript}" if transcript else ""
    question = (
        "直接描述这段10秒视频画面中的具体操作、界面内容和文字信息，不要复述指令。\n"
        "重要要求：\n"
        "1. 如果画面中有命令行/终端，必须抄写出可见的完整命令文本（包括URL、参数）\n"
        "2. 如果画面在滚动代码或切换页面，说明正在浏览什么内容、关键代码片段\n"
        "3. 如果画面中有菜单、选项列表或设置界面，列出可见的选项名称\n"
        "4. 所有屏幕上可见的重要文字信息（标题、按钮、提示语）都要体现在描述中"
        f"{transcript_hint}"
    )
    answer = _ask(model, ctx, sampler, vis, question, N_PREDICT)
    cleaned = _strip_think(answer.strip())
    if not cleaned or cleaned == "(无视觉描述)":
        print(f"    [WARN] empty caption, raw[:300]={repr(answer.strip()[:300])}")
        cleaned = "(无视觉描述)"
    return cleaned, vis


def _strip_think(text: str) -> str:
    import re
    for tag in ["<think", "\u003cthink"]:
        text = text.replace(tag + ">", "").replace(tag + ">\n", "")
    for tag in ["</think", "\u003c/think"]:
        text = text.replace(tag + ">", "").replace(tag + ">\n", "")
    sentences = re.split(r'(?<=[。！？\n])\s*', text)
    desc_verbs = ['显示', '展示', '包含', '列有', '背景', '顶部', '左侧', '中央', '底部', '中间']
    for i, s in enumerate(sentences):
        if s.startswith('画面') or s.startswith('屏幕'):
            for v in desc_verbs:
                if v in s[2:8]:
                    return ' '.join(sentences[i:]).strip()
    for i, s in enumerate(sentences):
        if any(s.startswith(k) for k in ['画面', '屏幕', '窗口']):
            return ' '.join(sentences[i:]).strip()
    return text.strip()


_pad_id_cache = None
def _ask(model, ctx, sampler, vis, question, n_predict):
    global _pad_id_cache
    if _pad_id_cache is None:
        _pad_id_cache = model.tokenize("<|image_pad|>", parse_special=True)[0]

    n_tiles = vis.shape[0] // 64
    tile_str = "<image>" + "<|image_pad|>" * 64 + "</image>"
    slice_str = "<slice>" + "<|image_pad|>" * 64 + "</slice>"

    if n_tiles == 1:
        image_str = tile_str
    else:
        image_str = tile_str + slice_str * (n_tiles - 1)

    prompt = f"<|im_start|>user\n{image_str}\n{question}<|im_end|>\n<|im_start|>assistant\n"
    tokens = model.tokenize(prompt, add_special=True, parse_special=True)

    segments = []
    current_text = []
    for tok in tokens:
        if tok == _pad_id_cache:
            if current_text:
                segments.append(("text", current_text))
                current_text = []
            if segments and segments[-1][0] == "visual":
                segments[-1] = ("visual", segments[-1][1] + 1)
            else:
                segments.append(("visual", 1))
        else:
            current_text.append(tok)
    if current_text:
        segments.append(("text", current_text))

    pos, vis_idx = 0, 0
    for stype, sdata in segments:
        if stype == "text":
            batch = minicpmv_llama.LlamaBatch(len(sdata), embd_dim=0)
            batch.set_tokens(sdata, pos_offset=pos)
            ctx.decode(batch)
            pos += len(sdata)
        else:
            n = sdata
            batch = minicpmv_llama.LlamaBatch(n, embd_dim=model.n_embd)
            batch.set_embd(vis[vis_idx:vis_idx + n], pos_offset=pos)
            ctx.decode(batch)
            vis_idx += n
            pos += n

    raw = bytearray()
    for _ in range(n_predict):
        tok = sampler.sample(ctx)
        sampler.accept(tok)
        if tok == model.eos_token:
            break
        raw.extend(model.detokenize(tok))
        ctx.decode_token(tok, pos=pos)
        pos += 1
    return raw.decode("utf-8", errors="replace")


def _full_transcript_text(entries):
    return "\n".join(f"[{int(e['start']//3600):02d}:{int(e['start']%3600//60):02d}:{int(e['start']%60):02d}] {e['text']}" for e in entries)
