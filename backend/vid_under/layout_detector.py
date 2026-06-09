# coding=utf-8
"""Pure-CV video frame layout detection."""
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image


@dataclass
class LayoutResult:
    layout_type: str
    content_bbox: tuple[int, int, int, int]
    confidence: float


_MIN_FRAMES = 3
_ANALYSIS_WIDTH = 480
_MOTION_Z = 1.8
_PIP_MAX_AREA = 0.22
_PIP_MIN_AREA = 0.015
_SPLIT_MIN_CONFIDENCE = 0.60
_UI_STRIP_MIN_UNIFORMITY = 0.85
_UI_STRIP_MIN_HEIGHT_RATIO = 0.03
_UI_STRIP_MAX_HEIGHT_RATIO = 0.12


def detect_layout(frames: list[Image.Image]) -> LayoutResult:
    if len(frames) < _MIN_FRAMES:
        raise ValueError("detect_layout requires at least 3 frames")

    arrays, original_size, scale = _prepare_frames(frames)
    variance = _temporal_variance(arrays)
    edge = _edge_density(arrays[0])

    pip = _detect_pip(variance, original_size, scale)
    side = _detect_side_by_side(arrays, variance, edge, original_size, scale)
    top_bottom = _detect_top_bottom(arrays, variance, edge, original_size, scale)

    candidates = [r for r in (pip, side, top_bottom) if r is not None]
    if candidates:
        best = max(candidates, key=lambda r: r.confidence)
        ow, oh = original_size
        bx, by, bw, bh = best.content_bbox
        if (bw * bh) / (ow * oh) >= 0.45:
            return best

    w, h = original_size
    return LayoutResult("fullscreen", (0, 0, w, h), 0.75)


def crop_content(frame: Image.Image, layout: LayoutResult) -> Image.Image:
    x, y, w, h = layout.content_bbox
    return frame.crop((x, y, x + w, y + h))


def _prepare_frames(frames: list[Image.Image]) -> tuple[list[np.ndarray], tuple[int, int], tuple[float, float]]:
    first = frames[0].convert("RGB")
    width, height = first.size
    analysis_w = min(width, _ANALYSIS_WIDTH)
    analysis_h = max(1, int(round(height * analysis_w / width)))
    arrays = []
    for frame in frames:
        rgb = frame.convert("RGB")
        if rgb.size != (width, height):
            rgb = rgb.resize((width, height), Image.BICUBIC)
        arr = np.array(rgb)
        if analysis_w != width:
            arr = cv2.resize(arr, (analysis_w, analysis_h), interpolation=cv2.INTER_AREA)
        arrays.append(arr)
    return arrays, (width, height), (width / analysis_w, height / analysis_h)


def _temporal_variance(frames: list[np.ndarray]) -> np.ndarray:
    gray = [cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY).astype(np.float32) for frame in frames]
    stack = np.stack(gray, axis=0)
    variance = np.var(stack, axis=0)
    return cv2.GaussianBlur(variance, (9, 9), 0)


def _edge_density(frame: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(sobel_x, sobel_y)
    return cv2.GaussianBlur(mag, (5, 5), 0)


def _detect_side_by_side(
    frames: list[np.ndarray],
    variance: np.ndarray,
    edge: np.ndarray,
    original_size: tuple[int, int],
    scale: tuple[float, float],
) -> LayoutResult | None:
    h, w = variance.shape
    profile = _smooth_1d(variance.mean(axis=0), max(9, w // 50))
    edge_profile = _smooth_1d(edge.mean(axis=0), max(9, w // 55))
    color_profile = _vertical_color_boundary_profile(frames)
    global_motion = float(np.percentile(profile, 90) + 1e-6)

    best = None
    for x in range(max(1, int(w * 0.25)), min(w - 1, int(w * 0.75))):
        left_motion = float(profile[:x].mean())
        right_motion = float(profile[x:].mean())
        motion_gap = abs(left_motion - right_motion) / global_motion
        if motion_gap < 0.12:
            continue

        left_edge = float(edge_profile[:x].mean())
        right_edge = float(edge_profile[x:].mean())
        content_left = _content_score(left_motion, left_edge, global_motion)
        content_right = _content_score(right_motion, right_edge, global_motion)
        boundary_score = float(color_profile[max(0, x - 2):min(w, x + 3)].mean())
        split_balance = min(x, w - x) / max(x, w - x)
        confidence = 0.38 * motion_gap + 0.26 * abs(content_left - content_right)
        confidence += 0.22 * boundary_score + 0.14 * split_balance
        if best is None or confidence > best[0]:
            best = (confidence, x, content_left >= content_right)

    if best is None or best[0] < _SPLIT_MIN_CONFIDENCE:
        return None

    confidence, x, use_left = best
    ow, oh = original_size
    ox = int(round(x * scale[0]))
    if use_left:
        bbox = (0, 0, _clamp_size(ox, ow), oh)
    else:
        bbox = (_clamp_size(ox, ow - 1), 0, ow - _clamp_size(ox, ow - 1), oh)
    return LayoutResult("side_by_side", bbox, _bounded_confidence(confidence))


def _detect_top_bottom(
    frames: list[np.ndarray],
    variance: np.ndarray,
    edge: np.ndarray,
    original_size: tuple[int, int],
    scale: tuple[float, float],
) -> LayoutResult | None:
    h, w = variance.shape
    profile = _smooth_1d(variance.mean(axis=1), max(9, h // 50))
    edge_profile = _smooth_1d(edge.mean(axis=1), max(9, h // 55))
    color_profile = _horizontal_color_boundary_profile(frames)
    global_motion = float(np.percentile(profile, 90) + 1e-6)

    best = None
    for y in range(max(1, int(h * 0.25)), min(h - 1, int(h * 0.75))):
        top_motion = float(profile[:y].mean())
        bottom_motion = float(profile[y:].mean())
        motion_gap = abs(top_motion - bottom_motion) / global_motion
        if motion_gap < 0.12:
            continue

        top_edge = float(edge_profile[:y].mean())
        bottom_edge = float(edge_profile[y:].mean())
        content_top = _content_score(top_motion, top_edge, global_motion)
        content_bottom = _content_score(bottom_motion, bottom_edge, global_motion)
        boundary_score = float(color_profile[max(0, y - 2):min(h, y + 3)].mean())
        split_balance = min(y, h - y) / max(y, h - y)
        confidence = 0.38 * motion_gap + 0.26 * abs(content_top - content_bottom)
        confidence += 0.22 * boundary_score + 0.14 * split_balance
        if best is None or confidence > best[0]:
            best = (confidence, y, content_top >= content_bottom)

    if best is None or best[0] < _SPLIT_MIN_CONFIDENCE:
        return None

    confidence, y, use_top = best
    ow, oh = original_size
    oy = int(round(y * scale[1]))
    if use_top:
        bbox = (0, 0, ow, _clamp_size(oy, oh))
    else:
        bbox = (0, _clamp_size(oy, oh - 1), ow, oh - _clamp_size(oy, oh - 1))
    return LayoutResult("top_bottom", bbox, _bounded_confidence(confidence))


def _detect_pip(
    variance: np.ndarray,
    original_size: tuple[int, int],
    scale: tuple[float, float],
) -> LayoutResult | None:
    h, w = variance.shape
    cutoff = max(float(variance.mean() + _MOTION_Z * variance.std()), float(np.percentile(variance, 92)))
    mask = (variance > cutoff).astype(np.uint8)
    kernel = np.ones((5, 5), dtype=np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    frame_area = h * w
    best = None
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        area_ratio = (bw * bh) / frame_area
        if area_ratio < _PIP_MIN_AREA or area_ratio > _PIP_MAX_AREA:
            continue
        if bw < w * 0.12 or bh < h * 0.12:
            continue

        near_corner = (x < w * 0.18 or x + bw > w * 0.82) and (y < h * 0.18 or y + bh > h * 0.82)
        if not near_corner:
            continue

        fill = float(cv2.contourArea(contour) / max(1, bw * bh))
        compact_area = 1.0 - min(area_ratio / _PIP_MAX_AREA, 1.0)
        confidence = 0.50 + 0.25 * fill + 0.25 * compact_area
        if best is None or confidence > best[0]:
            best = (confidence, x, y, bw, bh)

    if best is None:
        return None

    confidence, x, y, bw, bh = best
    ow, oh = original_size
    sx, sy = scale
    px = int(round(x * sx))
    py = int(round(y * sy))
    pw = int(round(bw * sx))
    ph = int(round(bh * sy))
    bbox = _content_bbox_excluding_overlay((ow, oh), (px, py, pw, ph))
    return LayoutResult("pip", bbox, _bounded_confidence(confidence))


def _content_bbox_excluding_overlay(frame_size: tuple[int, int], overlay: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    ow, oh = frame_size
    x, y, w, h = overlay
    candidates = [
        (0, 0, x, oh),
        (x + w, 0, ow - x - w, oh),
        (0, 0, ow, y),
        (0, y + h, ow, oh - y - h),
    ]
    candidates = [bbox for bbox in candidates if bbox[2] > ow * 0.35 and bbox[3] > oh * 0.35]
    if not candidates:
        return (0, 0, ow, oh)
    return max(candidates, key=lambda bbox: bbox[2] * bbox[3])


def _vertical_color_boundary_profile(frames: list[np.ndarray]) -> np.ndarray:
    median = np.median(np.stack(frames, axis=0), axis=0).astype(np.float32)
    hist = _color_histograms(median.astype(np.uint8), axis=0)
    diff = np.abs(np.diff(hist, axis=0)).sum(axis=1) * 0.5
    return _normalize_profile(np.pad(_smooth_1d(diff, max(9, len(diff) // 60)), (1, 0)))


def _horizontal_color_boundary_profile(frames: list[np.ndarray]) -> np.ndarray:
    median = np.median(np.stack(frames, axis=0), axis=0).astype(np.float32)
    hist = _color_histograms(median.astype(np.uint8), axis=1)
    diff = np.abs(np.diff(hist, axis=0)).sum(axis=1) * 0.5
    return _normalize_profile(np.pad(_smooth_1d(diff, max(9, len(diff) // 60)), (1, 0)))


def _color_histograms(frame: np.ndarray, axis: int) -> np.ndarray:
    labels = (frame[:, :, 0] // 32) * 64 + (frame[:, :, 1] // 32) * 8 + (frame[:, :, 2] // 32)
    if axis == 0:
        count, length = labels.shape[1], labels.shape[0]
        hist = np.zeros((count, 512), dtype=np.float32)
        for i in range(count):
            hist[i] = np.bincount(labels[:, i], minlength=512)
    else:
        count, length = labels.shape[0], labels.shape[1]
        hist = np.zeros((count, 512), dtype=np.float32)
        for i in range(count):
            hist[i] = np.bincount(labels[i, :], minlength=512)
    return hist / max(1, length)


def _content_score(motion: float, edge: float, motion_scale: float) -> float:
    static_score = 1.0 - min(motion / max(motion_scale, 1e-6), 1.0)
    edge_score = min(edge / 80.0, 1.0)
    return 0.65 * static_score + 0.35 * edge_score


def _smooth_1d(values: np.ndarray, window: int) -> np.ndarray:
    window = max(3, int(window) | 1)
    if values.size < window:
        return values.astype(np.float32)
    kernel = np.ones(window, dtype=np.float32) / window
    return np.convolve(values.astype(np.float32), kernel, mode="same")


def _normalize_profile(values: np.ndarray) -> np.ndarray:
    values = values.astype(np.float32)
    lo = float(np.percentile(values, 5))
    hi = float(np.percentile(values, 95))
    if hi <= lo + 1e-6:
        return np.zeros_like(values, dtype=np.float32)
    return np.clip((values - lo) / (hi - lo), 0.0, 1.0)


def _clamp_size(value: int, limit: int) -> int:
    return max(1, min(int(value), int(limit)))


def _bounded_confidence(value: float) -> float:
    return float(np.clip(value, 0.0, 0.99))


def detect_ui_strips(frame: Image.Image) -> tuple[int, int, int, int] | None:
    """Check if frame has uniform-color strips at edges (player controls, title bars).

    Returns (x, y, w, h) of content area with UI strips removed, or None.
    """
    arr = np.array(frame.convert("RGB"))
    h, w = arr.shape[:2]

    top_crop = _find_uniform_strip(arr, "top")
    bottom_crop = _find_uniform_strip(arr, "bottom")
    left_crop = _find_uniform_strip(arr, "left")
    right_crop = _find_uniform_strip(arr, "right")

    x = left_crop
    y = top_crop
    cw = w - left_crop - right_crop
    ch = h - top_crop - bottom_crop

    if cw < w * 0.5 or ch < h * 0.5:
        return None
    if top_crop + bottom_crop + left_crop + right_crop < h * 0.02:
        return None
    return (x, y, cw, ch)


def _find_uniform_strip(arr: np.ndarray, side: str) -> int:
    """Return pixels to crop from one side where color is uniform."""
    h, w = arr.shape[:2]
    if side == "top":
        max_px = int(h * _UI_STRIP_MAX_HEIGHT_RATIO)
        for y in range(max_px):
            row = arr[y].astype(np.float32)
            std = row.std()
            if std > 30:
                return y
        return max_px
    elif side == "bottom":
        max_px = int(h * _UI_STRIP_MAX_HEIGHT_RATIO)
        for y in range(max_px):
            row = arr[h - 1 - y].astype(np.float32)
            std = row.std()
            if std > 30:
                return y
        return max_px
    elif side == "left":
        max_px = int(w * _UI_STRIP_MAX_HEIGHT_RATIO)
        for x in range(max_px):
            col = arr[:, x].astype(np.float32)
            std = col.std()
            if std > 30:
                return x
        return max_px
    elif side == "right":
        max_px = int(w * _UI_STRIP_MAX_HEIGHT_RATIO)
        for x in range(max_px):
            col = arr[:, w - 1 - x].astype(np.float32)
            std = col.std()
            if std > 30:
                return x
        return max_px
    return 0


def get_vision_bbox(frame: Image.Image, provider: str = "gemini") -> tuple[int, int, int, int] | None:
    """Use a vision model to get the content bbox for this frame.

    Returns (x, y, w, h) or None on failure.
    """
    from external_api import call_vision_for_corners, _pil_to_base64
    import json

    w, h = frame.size
    b64 = _pil_to_base64(frame)
    corners = call_vision_for_corners(b64, w, h, provider=provider)
    if corners is None:
        return None

    order = ("top_left", "top_right", "bottom_right", "bottom_left")
    try:
        pts = [(corners[k]["x"], corners[k]["y"]) for k in order]
    except (KeyError, TypeError):
        return None

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x1, y1 = min(xs), min(ys)
    x2, y2 = max(xs), max(ys)
    bw, bh = x2 - x1, y2 - y1

    if bw < w * 0.3 or bh < h * 0.3:
        return None
    return (int(x1), int(y1), int(bw), int(bh))
