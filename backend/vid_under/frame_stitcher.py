# coding=utf-8
"""
Scrolling frame deduplication and stitching for inspect_scrolling.

Algorithm: hybrid cascade
  1. pHash dedup: drop near-duplicate frames (cursor blink tolerance)
  2. Sobel edge map + multi-scale NCC: estimate scroll offset between consecutive frames
  3. Phase correlation: fallback when NCC fails
  4. Seam finding: cut at minimum-difference row in overlap zone
  5. Strip stitching: append only new content from each frame

References:
  - mate-matt/screenshot-stitcher: multi-scale NCC + Sobel edge + row profile
  - id-fa/stitch-candidates: FFT phase correlation + optical flow
  - jbonney/scrollshot: row-by-row voting for terminal text
"""
import numpy as np
from PIL import Image
import cv2

# ── Thresholds ──────────────────────────────────────────────────
_PHASH_THRESHOLD = 3          # perceptual hash distance for near-dup
_CHANGED_RATIO_MAX = 0.005    # max changed pixel ratio for cursor blink
_NCC_SCORE_MIN = 0.45         # minimum NCC score to trust offset
_PHASE_RESPONSE_MIN = 0.05    # minimum phase correlation response
_MAX_DX = 20                  # max horizontal drift allowed
_MIN_OVERLAP_FRAC = 0.05      # min overlap as fraction of frame height
_MAX_OVERLAP_FRAC = 0.95      # max overlap (near-duplicate → dedup)


# ── Preprocessing ───────────────────────────────────────────────

def _to_gray(img: Image.Image) -> np.ndarray:
    """PIL Image → grayscale uint8 numpy."""
    return np.array(img.convert("L"))


def _preprocess(gray: np.ndarray, x_margin: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """Returns (gray_cropped, sobel_edge_cropped)."""
    h, w = gray.shape
    if w > 2 * x_margin:
        gray = gray[:, x_margin:-x_margin]
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    sobel = cv2.Sobel(blurred, cv2.CV_16S, 0, 1, ksize=3)
    edge = cv2.convertScaleAbs(sobel)
    return blurred, edge


# ── Step 1: pHash dedup ────────────────────────────────────────

def _is_near_duplicate(a: Image.Image, b: Image.Image) -> bool:
    """True if frames are near-identical (allows cursor blink)."""
    ha = _compute_phash(a)
    hb = _compute_phash(b)
    if _hash_distance(ha, hb) > _PHASH_THRESHOLD:
        return False
    # Also check pixel-level change ratio to distinguish cursor blink from real scroll
    ga = _to_gray(a).astype(np.int16)
    gb = _to_gray(b).astype(np.int16)
    diff = np.abs(ga - gb)
    changed_ratio = (diff > 35).mean()
    return changed_ratio < _CHANGED_RATIO_MAX


def _compute_phash(img: Image.Image) -> int:
    gray = np.array(img.convert("L").resize((32, 32)), dtype=np.float32)
    dct = cv2.dct(gray)
    low = dct[:8, :8].copy()
    median = np.median(low[1:])
    bits = low > median
    value = 0
    for bit in bits.ravel():
        value = (value << 1) | int(bit)
    return value


def _hash_distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def deduplicate_frames(frames: list[Image.Image]) -> list[Image.Image]:
    """Remove near-duplicate frames (static frames, cursor blinks)."""
    if len(frames) <= 1:
        return frames
    kept = [frames[0]]
    for f in frames[1:]:
        if not _is_near_duplicate(kept[-1], f):
            kept.append(f)
    return kept


# ── Step 2: Multi-scale NCC offset estimation ──────────────────

def _ncc_offset(
    prev_edge: np.ndarray,
    curr_edge: np.ndarray,
    template_heights: list[int] | None = None,
) -> tuple[float, int, int, int] | None:
    """
    Estimate vertical scroll offset using multi-scale NCC on edge maps.

    Returns (score, offset_y, overlap_height, template_height) or None.
    offset_y > 0 means content scrolled down (prev bottom matches curr top).
    """
    h_prev, w_prev = prev_edge.shape
    h_curr, w_curr = curr_edge.shape
    w = min(w_prev, w_curr)

    prev_e = prev_edge[:, :w]
    curr_e = curr_edge[:, :w]

    h = min(h_prev, h_curr)
    if template_heights is None:
        template_heights = [80, 160, 240, 360, 500]
        # Add a height proportional to frame
        proportional = min(700, h // 2)
        if proportional >= 80:
            template_heights.append(proportional)

    best = None
    for th in sorted(set(th for th in template_heights if 32 <= th < h)):
        template = prev_e[-th:, :]
        # Search in top portion of current frame (where overlap would be)
        search_h = min(h, max(th + 20, int(h * 0.95)))
        search = curr_e[:search_h, :]

        if search.shape[0] < template.shape[0]:
            continue

        # Match template — single column result since template spans full width
        res = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)

        y_in_curr = loc[1]
        # offset_y: how many new pixels at top of current frame
        offset_y = h_prev - th - y_in_curr
        overlap = h_prev - offset_y

        # Sanity: overlap must be reasonable fraction
        if overlap < h * _MIN_OVERLAP_FRAC or overlap > h * _MAX_OVERLAP_FRAC:
            continue

        candidate = (score, int(offset_y), int(overlap), int(th))
        if best is None or candidate[0] > best[0]:
            best = candidate

    return best


# ── Step 3: Phase correlation fallback ─────────────────────────

def _phase_offset(
    prev_edge: np.ndarray,
    curr_edge: np.ndarray,
) -> tuple[float, float, float] | None:
    """
    FFT phase correlation to estimate (dx, dy, response).
    Returns None if it fails.
    """
    h = min(prev_edge.shape[0], curr_edge.shape[0])
    w = min(prev_edge.shape[1], curr_edge.shape[1])

    a = prev_edge[:h, :w].astype(np.float32)
    b = curr_edge[:h, :w].astype(np.float32)

    # Hanning window reduces spectral leakage
    win = cv2.createHanningWindow((w, h), cv2.CV_32F)
    result = cv2.phaseCorrelate(a, b, win)
    if result is None:
        return None
    (dx, dy), response = result
    return float(dx), float(dy), float(response)


# ── Step 4: Seam finding ───────────────────────────────────────

def _find_seam_row(
    prev_gray: np.ndarray,
    curr_gray: np.ndarray,
    overlap: int,
    margin: int = 4,
) -> int:
    """
    Find the row in the overlap zone with minimum difference.
    Returns the row index within the overlap (0 = top of overlap).
    """
    w = min(prev_gray.shape[1], curr_gray.shape[1])
    # Overlap zone: prev[-overlap:] matches curr[:overlap]
    prev_strip = prev_gray[-overlap:, :w].astype(np.int16)
    curr_strip = curr_gray[:overlap, :w].astype(np.int16)

    n_rows = min(prev_strip.shape[0], curr_strip.shape[0])
    if n_rows <= 2 * margin:
        return n_rows // 2

    scores = np.zeros(n_rows, dtype=np.float64)
    for r in range(margin, n_rows - margin):
        diff = np.abs(prev_strip[r].astype(np.int16) - curr_strip[r].astype(np.int16))
        scores[r] = diff.mean()

    best = int(np.argmin(scores[margin:-margin])) + margin
    return best


# ── Step 5: Stitch frames ──────────────────────────────────────

def _estimate_scroll(
    prev: Image.Image,
    curr: Image.Image,
) -> dict | None:
    """Estimate scroll offset between two frames. Returns dict or None."""
    prev_gray = _to_gray(prev)
    curr_gray = _to_gray(curr)
    _, prev_edge = _preprocess(prev_gray)
    _, curr_edge = _preprocess(curr_gray)

    # Try NCC first
    ncc = _ncc_offset(prev_edge, curr_edge)
    if ncc and ncc[0] > _NCC_SCORE_MIN:
        score, offset_y, overlap, th = ncc
        return {
            "method": "ncc_edge",
            "offset_y": offset_y,
            "overlap": overlap,
            "score": score,
            "prev_gray": prev_gray,
            "curr_gray": curr_gray,
        }

    # Fallback: phase correlation
    phase = _phase_offset(prev_edge, curr_edge)
    if phase and phase[2] > _PHASE_RESPONSE_MIN and abs(phase[0]) < _MAX_DX:
        dx, dy, resp = phase
        offset_y = int(round(dy))
        overlap = prev_gray.shape[0] - offset_y
        if overlap > prev_gray.shape[0] * _MIN_OVERLAP_FRAC:
            return {
                "method": "phase",
                "offset_y": offset_y,
                "overlap": overlap,
                "score": resp,
                "prev_gray": prev_gray,
                "curr_gray": curr_gray,
            }

    return None


def stitch_scrolling_frames(
    frames: list[Image.Image],
    min_offset: int = 2,
) -> Image.Image:
    """
    Stitch scrolling frames into a single long image, deduplicating overlap.

    Args:
        frames: List of PIL Images (already deduped).
        min_offset: Minimum pixel offset to consider as real scroll.

    Returns:
        Single stitched PIL Image.
    """
    if not frames:
        raise ValueError("No frames to stitch")
    if len(frames) == 1:
        return frames[0]

    # Start with first frame
    stitched = np.array(frames[0].convert("RGB"))

    stats = {}

    for i in range(1, len(frames)):
        curr = frames[i]
        prev_img = Image.fromarray(stitched)

        result = _estimate_scroll(prev_img, curr)

        if result is None:
            # No overlap detected — naive concat with small gap
            gap = np.full((3, stitched.shape[1], 3), 255, dtype=np.uint8)
            stitched = np.concatenate([stitched, gap, np.array(curr.convert("RGB"))], axis=0)
            stats["naive"] = stats.get("naive", 0) + 1
            continue

        offset_y = result["offset_y"]
        overlap = result["overlap"]
        method = result["method"]

        if offset_y <= min_offset:
            # Essentially no new content
            stats["skipped"] = stats.get("skipped", 0) + 1
            continue

        curr_rgb = np.array(curr.convert("RGB"))
        h_prev = stitched.shape[0]
        h_curr = curr_rgb.shape[0]
        w = min(stitched.shape[1], curr_rgb.shape[1])

        # Find best seam row in overlap zone
        prev_gray = result["prev_gray"]
        curr_gray = result["curr_gray"]
        seam = _find_seam_row(prev_gray, curr_gray, overlap)

        # Take: all of stitched, then from seam to end of current frame
        # The overlap zone in prev is prev[-overlap:]
        # The overlap zone in curr is curr[:overlap]
        # seam=0 means cut at very top of overlap → take all of prev, all of curr
        # seam=overlap means cut at bottom → take all of prev, none of overlap, rest of curr

        # New content from current frame starts at overlap + new stuff
        new_start = overlap  # where new content begins in current frame
        # But we want to blend at the seam: take prev up to (h_prev - overlap + seam),
        # then curr from seam onward
        cut_prev = h_prev - overlap + seam
        if cut_prev < 0:
            cut_prev = 0

        # Build result
        top_part = stitched[:cut_prev]
        bottom_part = curr_rgb[seam:]
        new_w = max(top_part.shape[1], bottom_part.shape[1])

        # Pad to same width if needed
        if top_part.shape[1] < new_w:
            pad = np.full((top_part.shape[0], new_w - top_part.shape[1], 3), 255, dtype=np.uint8)
            top_part = np.concatenate([top_part, pad], axis=1)
        if bottom_part.shape[1] < new_w:
            pad = np.full((bottom_part.shape[0], new_w - bottom_part.shape[1], 3), 255, dtype=np.uint8)
            bottom_part = np.concatenate([bottom_part, pad], axis=1)

        stitched = np.concatenate([top_part, bottom_part], axis=0)
        stats[method] = stats.get(method, 0) + 1

    print(f"  [stitch] stats: {stats}, output={stitched.shape[1]}x{stitched.shape[0]}")

    return Image.fromarray(stitched)
