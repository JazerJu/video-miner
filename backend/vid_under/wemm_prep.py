# -*- coding: utf-8 -*-
"""WeMM-Embedding 输入预处理的 numpy 实现（不依赖 torch），逐步复刻 torch 流水线：
qwen_vl_utils.fetch_video（decord 取帧 + torchvision 抗锯齿 bicubic 缩放）
-> Qwen3VLVideoProcessor（归一化、时间维补帧、切 patch）
-> Qwen3VLProcessor（每两帧一段、带时间戳的占位 token）
-> Qwen3_5Model.get_rope_index（M-RoPE 三维位置）。"""
import json
import math
import os
import subprocess

import numpy as np

PATCH, MERGE, TEMPORAL = 16, 2, 2
FACTOR = PATCH * MERGE                       # 32
FPS_DEFAULT, FRAME_FACTOR, FPS_MIN_FRAMES, FPS_MAX_FRAMES = 2.0, 2, 4, 768
VIDEO_MIN_TOKEN_NUM, VIDEO_MAX_TOKEN_NUM = 128, 768
MODEL_SEQ_LEN = 128000
IMAGE_TOKEN, VIDEO_TOKEN, VISION_START = 248056, 248057, 248053


# ---------- 取帧 ----------
def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
                          "-show_entries", "stream=width,height,avg_frame_rate,nb_read_packets",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = s["avg_frame_rate"].split("/")
    return int(s["width"]), int(s["height"]), float(num) / float(den), int(s["nb_read_packets"])


def decode_rgb(path, width, height):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-vsync", "0", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, height, width, 3)


def smart_nframes(total_frames, video_fps, fps=FPS_DEFAULT):
    min_frames = math.ceil(FPS_MIN_FRAMES / FRAME_FACTOR) * FRAME_FACTOR
    max_frames = math.floor(min(FPS_MAX_FRAMES, total_frames) / FRAME_FACTOR) * FRAME_FACTOR
    n = total_frames / video_fps * fps
    n = min(min(max(n, min_frames), max_frames), total_frames)
    n = math.floor(n / FRAME_FACTOR) * FRAME_FACTOR
    if not (FRAME_FACTOR <= n <= total_frames):
        raise ValueError(f"nframes should be in [{FRAME_FACTOR}, {total_frames}], got {n}")
    return n


def smart_resize(height, width, factor, min_pixels, max_pixels):
    h_bar = max(factor, round(height / factor) * factor)
    w_bar = max(factor, round(width / factor) * factor)
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = math.floor(height / beta / factor) * factor
        w_bar = math.floor(width / beta / factor) * factor
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = math.ceil(height * beta / factor) * factor
        w_bar = math.ceil(width * beta / factor) * factor
    return h_bar, w_bar


# ---------- torch 的抗锯齿 bicubic（aten::_upsample_bicubic2d_aa，与 PIL 同一套滤波） ----------
def _cubic(x, a=-0.5):
    x = np.abs(x)
    return np.where(x < 1, ((a + 2) * x - (a + 3)) * x * x + 1, np.where(x < 2, (((x - 5) * x + 8) * x - 4) * a, 0.0))


def _aa_weights(in_size, out_size):
    scale = in_size / out_size
    support = 2.0 * scale if scale >= 1.0 else 2.0
    invscale = 1.0 / scale if scale >= 1.0 else 1.0
    size = int(math.ceil(support)) * 2 + 1
    idx = np.zeros((out_size, size), np.int64)
    w = np.zeros((out_size, size), np.float64)
    for i in range(out_size):
        center = scale * (i + 0.5)
        xmin = max(int(center - support + 0.5), 0)
        xsize = min(int(center + support + 0.5), in_size) - xmin
        ww = _cubic((np.arange(xsize) + xmin - center + 0.5) * invscale)
        total = ww.sum()
        if total != 0:
            ww = ww / total
        idx[i, :xsize] = np.arange(xsize) + xmin
        w[i, :xsize] = ww
    return idx, w


def _resize_axis(x, axis, out_size):
    """沿一个轴做抗锯齿 bicubic：权重排成稠密矩阵，整块数据做一次 BLAS 矩阵乘法。"""
    in_size = x.shape[axis]
    idx, w = _aa_weights(in_size, out_size)
    dense = np.zeros((out_size, in_size), np.float32)
    for i in range(out_size):
        np.add.at(dense[i], idx[i], w[i].astype(np.float32))
    moved = np.moveaxis(x, axis, -1)
    flat = np.ascontiguousarray(moved).reshape(-1, in_size)
    out = (flat @ dense.T).reshape(moved.shape[:-1] + (out_size,))
    return np.moveaxis(out, -1, axis)


def resize_bicubic_aa(frames, out_h, out_w):
    """frames: uint8 [T,H,W,C] -> 与 torchvision resize(uint8 张量, BICUBIC, antialias=True) 一致的 uint8 结果。"""
    x = frames.astype(np.float32)
    if x.shape[2] != out_w:
        x = _resize_axis(x, 2, out_w)
    if x.shape[1] != out_h:
        x = _resize_axis(x, 1, out_h)
    return np.clip(np.round(x), 0, 255).astype(np.uint8)


def load_video(path, fps=FPS_DEFAULT, video_max_tokens=VIDEO_MAX_TOKEN_NUM):
    width, height, video_fps, total = probe(path)
    frames = decode_rgb(path, width, height)
    total = len(frames)
    nframes = smart_nframes(total, video_fps, fps)
    idx = np.round(np.linspace(0, total - 1, nframes)).astype(np.int64)
    frames = frames[idx]
    min_pixels = VIDEO_MIN_TOKEN_NUM * FACTOR * FACTOR
    total_pixels = MODEL_SEQ_LEN * FACTOR * FACTOR * 0.9
    max_pixels = max(min(video_max_tokens * FACTOR * FACTOR, total_pixels / nframes * FRAME_FACTOR), int(min_pixels * 1.05))
    rh, rw = smart_resize(height, width, FACTOR, min_pixels, max_pixels)
    frames = resize_bicubic_aa(frames, rh, rw)
    return frames, {"fps": video_fps, "frames_indices": idx.tolist()}


# ---------- 视频处理器：归一化 + 切 patch ----------
def video_patches(frames):
    """uint8 [T,H,W,C] -> (pixel_values [N, 3*2*16*16] float32, grid_thw [t,h,w])"""
    x = frames.astype(np.float32).transpose(0, 3, 1, 2)          # T,C,H,W
    x = x * np.float32(1 / 255.0)
    x = (x - np.float32(0.5)) / np.float32(0.5)
    T, C, H, W = x.shape
    if pad := -T % TEMPORAL:
        x = np.concatenate([x, np.repeat(x[-1:], pad, axis=0)], axis=0)
    gt, gh, gw = x.shape[0] // TEMPORAL, H // PATCH, W // PATCH
    x = x.reshape(1, gt, TEMPORAL, C, gh // MERGE, MERGE, PATCH, gw // MERGE, MERGE, PATCH)
    x = x.transpose(0, 1, 4, 7, 5, 8, 3, 2, 6, 9)
    return np.ascontiguousarray(x.reshape(gt * gh * gw, C * TEMPORAL * PATCH * PATCH)), (gt, gh, gw)


def timestamps(indices, video_fps, merge=TEMPORAL):
    indices = list(indices)
    if len(indices) % merge:
        indices.extend(indices[-1] for _ in range(merge - len(indices) % merge))
    ts = [i / video_fps for i in indices]
    return [(ts[i] + ts[i + merge - 1]) / 2 for i in range(0, len(ts), merge)]


# ---------- 文本 ----------
class Prompter:
    def __init__(self, tokenizer_json):
        from tokenizers import Tokenizer
        self.tok = Tokenizer.from_file(tokenizer_json)

    def build(self, text=None, video=None):
        """text: str | None；video: (grid_thw, metadata) | None。返回 input_ids (int64 [L])。
        模板与 Sentence Transformers 的 embedding 模板一致：内容里文字在前、视频在后。"""
        content = ""
        if text:
            content += text
        if video is not None:
            (gt, gh, gw), meta = video
            frame_seqlen = gh * gw // (MERGE * MERGE)
            ts = timestamps(meta["frames_indices"], meta["fps"])
            for i in range(gt):
                content += f"<{ts[i]:.1f} seconds><|vision_start|>" + "<|video_pad|>" * frame_seqlen + "<|vision_end|>"
        prompt = "<|im_start|>user\n" + content + "<|im_end|>\n"
        return np.array(self.tok.encode(prompt, add_special_tokens=True).ids, np.int64)


# ---------- M-RoPE 位置（Qwen3.5：每段视频帧当作 t=1 的一组） ----------
def rope_index(input_ids, video_grid_thw=None):
    ids = input_ids.tolist()
    groups = []
    if video_grid_thw is not None:
        gt, gh, gw = video_grid_thw
        groups = [(1, gh, gw)] * gt
    starts = [i for i, t in enumerate(ids[:-1]) if t == VISION_START and ids[i + 1] == VIDEO_TOKEN]
    parts, st, next_pos = [], 0, 0
    for (t, h, w) in groups:
        ed = ids.index(VIDEO_TOKEN, st)
        lh, lw = h // MERGE, w // MERGE
        text_len = ed - st
        parts.append(np.broadcast_to(np.arange(text_len) + next_pos, (3, text_len)))
        base = next_pos + text_len
        hh = np.repeat(np.arange(lh), lw)
        ww = np.tile(np.arange(lw), lh)
        vis = np.stack([np.zeros(lh * lw, np.int64), hh, ww]) + base
        parts.append(vis)
        next_pos = int(vis.max()) + 1
        st = ed + lh * lw
    assert len(starts) == len(groups), (len(starts), len(groups))
    if st < len(ids):
        n = len(ids) - st
        parts.append(np.broadcast_to(np.arange(n) + next_pos, (3, n)))
    return np.concatenate(parts, axis=1).astype(np.int64)[:, None, :]      # [3, 1, L]


def prepare(prompter, text=None, video_path=None, fps=FPS_DEFAULT, video_max_tokens=VIDEO_MAX_TOKEN_NUM):
    pixel_values = grid = None
    video = None
    if video_path:
        frames, meta = load_video(video_path, fps, video_max_tokens)
        pixel_values, grid = video_patches(frames)
        video = (grid, meta)
    ids = prompter.build(text=text, video=video)
    return {"input_ids": ids, "pixel_values": pixel_values, "grid_thw": grid, "position_ids": rope_index(ids, grid)}
