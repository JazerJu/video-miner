# coding=utf-8
import numpy as np
from PIL import Image
import cv2
from pathlib import Path
import re
import zlib
from external_api import call_glm_ocr

# GLM-OCR only ever shrinks (glm_ocr_onnx._smart_resize caps input at this many pixels and passes
# smaller images through). A 852x480 screen recording is read at 41% of the cap and dense editor text
# comes back as repetition loops; going past the cap (2x) overflows the vision encoder (4.4 GB buffer).
GLM_OCR_MAX_PIXELS = 1_000_000
OCR_LOOP_COPIES = 5        # repeated this many times in a row: a decoder loop, not screen content
OCR_RUNAWAY_CHARS = 200    # a line longer than this that also compresses below
OCR_RUNAWAY_RATIO = 0.15   # this ratio is one phrase over and over (loops 0.01-0.03, prose 0.5-0.65)


def _upscale_to_ocr_cap(img):
    w, h = img.size
    if w * h >= GLM_OCR_MAX_PIXELS:
        return img
    k = (GLM_OCR_MAX_PIXELS / (w * h)) ** 0.5 * 0.995
    return img.resize((round(w * k), round(h * k)), Image.Resampling.LANCZOS)


def _runaway(line):
    s = line.strip()
    b = s.encode()
    return len(s) > OCR_RUNAWAY_CHARS and len(zlib.compress(b)) / len(b) < OCR_RUNAWAY_RATIO


def _is_count_run(lines):
    """Lines identical but for numbers, every number column constant or stepping evenly
    (180, 190, 200 ...): the decoder counting up. A table of measured values never steps evenly."""
    cols = [[float(x) for x in re.findall(r"\d+(?:\.\d+)?", l)] for l in lines]
    if len({len(c) for c in cols}) != 1 or not cols[0]:
        return False
    stepping = False
    for col in zip(*cols):
        steps = {round(b - a, 6) for a, b in zip(col, col[1:])}
        if len(steps) != 1:
            return False
        stepping = stepping or steps != {0}
    return stepping


def _collapse_runs(lines):
    """Keep one copy of every decoder loop: a block of up to 8 lines repeated OCR_LOOP_COPIES+ times in
    a row verbatim, or OCR_LOOP_COPIES+ lines counting up. Shorter repeats are real content (code
    and tables repeat lines: `fi`, `"Rest for 60 minutes",` three times) and stay."""
    exact = [l.strip() for l in lines]
    folded = [re.sub(r"\d+", "#", s) for s in exact]
    out, i = [], 0
    while i < len(lines):
        for p in range(1, 9):
            block = exact[i:i + p]
            if len(block) < p or (p == 1 and len(block[0]) < 15):
                continue
            n = 1
            while exact[i + n * p:i + (n + 1) * p] == block:
                n += 1
            if n >= OCR_LOOP_COPIES:
                out.extend(lines[i:i + p])
                i += n * p
                break
        else:
            n = 1
            while i + n < len(lines) and folded[i + n] == folded[i]:
                n += 1
            out.append(lines[i])
            if n >= OCR_LOOP_COPIES and len(folded[i]) >= 15 and _is_count_run(exact[i:i + n]):
                i += n
            else:
                i += 1
    return out


def _ocr_looped(text, hit_limit):
    lines = [l for l in text.splitlines() if l.strip()]
    if hit_limit or any(_runaway(l) for l in lines):
        return True
    return len(_collapse_runs(lines)) < len(lines)


def _trim_ocr_loop(text, hit_limit):
    """Strip decoder loops from an OCR output: everything from a runaway line on, the line max_tokens
    cut off, and every repeated or counting block down to one copy."""
    lines = text.splitlines()
    for i, l in enumerate(lines):
        if _runaway(l):
            lines, hit_limit = lines[:i], False
            break
    ne = [l for l in lines if l.strip()]
    if hit_limit and ne:
        ne = ne[:-1]   # cut off mid-line by max_tokens
    return "\n".join(_collapse_runs(ne)).strip()


def _ocr_code_frame(img, prompt):
    """OCR a code frame scaled up to the GLM-OCR cap. If that loops, read the top and bottom halves
    separately (each scaled to the cap again, ~2.2x for 480p) and cut whatever still loops."""
    text, hit = call_glm_ocr(_upscale_to_ocr_cap(img), prompt, return_hit_limit=True)
    if not _ocr_looped(text, hit):
        return text
    w, h = img.size
    parts = []
    for box in ((0, 0, w, h // 2 + 10), (0, h // 2 - 10, w, h)):
        t, hit = call_glm_ocr(_upscale_to_ocr_cap(img.crop(box)), prompt, return_hit_limit=True)
        parts.append(_trim_ocr_loop(t, hit) if _ocr_looped(t, hit) else t.strip())
    return "\n".join(p for p in parts if p)


def _pil_to_cv2(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


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


def _frame_quality_score(img: Image.Image) -> float:
    """Score frame quality: sharpness + edge density + color diversity."""
    gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    h, w = gray.shape

    # Laplacian variance (blur detection)
    lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()

    # Edge density (content richness via Canny)
    edges = cv2.Canny(gray, 50, 150)
    edge_ratio = np.count_nonzero(edges) / (h * w)

    # Color diversity (unique colors / total pixels, downsampled)
    small = gray[::4, ::4]
    unique_ratio = len(np.unique(small)) / small.size

    return lap_var * (0.3 + edge_ratio * 5.0) * (0.5 + unique_ratio * 2.0)


def _pick_best_frame(frames: list[Image.Image]) -> Image.Image:
    """From a clip's frames, pick the sharpest, most content-rich one."""
    if len(frames) <= 1:
        return frames[0]

    scores = [_frame_quality_score(f) for f in frames]
    best_idx = int(np.argmax(scores))
    return frames[best_idx]


def _is_low_quality(img: Image.Image, min_lap_var: float = 50.0,
                    min_edge_ratio: float = 0.01) -> bool:
    """Return True if frame is too blurry or too empty to be a useful slide."""
    gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    h, w = gray.shape

    lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    if lap_var < min_lap_var:
        return True

    edges = cv2.Canny(gray, 50, 150)
    edge_ratio = np.count_nonzero(edges) / (h * w)
    if edge_ratio < min_edge_ratio:
        return True

    return False


# Paging by "ink": pixels at least SLIDE_INK_DELTA grey levels away from the frame's background.
# Measured on a 14-min full-screen PPT course (video 478): animation adding to a page keeps >= 0.99 of
# the previous frame's ink, every real page turn keeps <= 0.74. pHash could not tell them apart: the
# same page drifted 18-22 bits as it filled in, while a turn that kept the figure moved only 6.
SLIDE_INK_DELTA = 40
SLIDE_TURN_KEEP = 0.8       # less of the previous frame's ink survives: the page turned
SLIDE_OVERLAY_KEEP = 0.95   # the frame after keeps the one before this well: this one was a pop-up
SLIDE_SAME_KEEP = 0.95      # two pages keeping each other's ink this well are one page shown twice


def _ink_mask(img: Image.Image) -> np.ndarray:
    g = np.asarray(img.convert("L").resize((342, 192)), dtype=np.int16)
    return np.abs(g - np.bincount(g.ravel()).argmax()) > SLIDE_INK_DELTA


def _ink_keep(a: np.ndarray, b: np.ndarray) -> float:
    """Share of a's ink that is still ink in b."""
    return float((a & b).sum()) / max(int(a.sum()), 1)


def extract_unique_slides(
    clip_frames: dict[int, list[Image.Image]],
    clip_captions: dict[int, str],
    output_dir: str | None = None,
) -> list[dict]:
    """
    Split slide clips into pages and keep one image per page: its last frame, i.e. the page with all
    its animation shown, dated to when the page first appeared.

    Args:
        clip_frames: {clip_idx: [PIL.Image, ...]}
        clip_captions: {clip_idx: "caption text"} (unused)
        output_dir: if set, save slide images to this directory

    Returns:
        list of {"time": float, "image": PIL.Image, "clip_idx": int, "phash": str}
    """
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    items = []
    for clip_idx in sorted(clip_frames.keys()):
        frames = clip_frames[clip_idx]
        if not frames:
            continue
        frame = _pick_best_frame(frames)
        if _is_low_quality(frame):
            continue
        items.append((clip_idx, frame, _ink_mask(frame)))

    # A page turns when most of the previous frame's ink is gone. Animation only adds ink, so the page
    # keeps its latest frame, the fullest one; its time stays the first clip it appeared in.
    pages = []
    prev_ink = None
    for k, (clip_idx, frame, ink) in enumerate(items):
        if prev_ink is not None and _ink_keep(prev_ink, ink) < SLIDE_TURN_KEEP:
            if k + 1 < len(items) and _ink_keep(prev_ink, items[k + 1][2]) >= SLIDE_OVERLAY_KEEP:
                continue   # a pop-up over the page (a terminal, a dialog); the next frame is back
            pages.append({"clip_idx": clip_idx, "image": frame, "ink": ink})
        elif not pages:
            pages.append({"clip_idx": clip_idx, "image": frame, "ink": ink})
        else:
            pages[-1]["image"], pages[-1]["ink"] = frame, ink
        prev_ink = ink

    # the lecturer going back to an earlier page gives the same page twice
    unique_slides = []
    for page in pages:
        if any(_ink_keep(page["ink"], s["ink"]) >= SLIDE_SAME_KEEP and
               _ink_keep(s["ink"], page["ink"]) >= SLIDE_SAME_KEEP for s in unique_slides):
            continue
        unique_slides.append(page)
    for slide in unique_slides:
        slide.pop("ink")
        slide["time"] = 0.0
        slide["phash"] = f"{_compute_phash(slide['image']):016x}"

    if output_dir:
        for i, slide in enumerate(unique_slides):
            path = Path(output_dir) / f"slide_{i:03d}.png"
            slide["image"].save(str(path))
            slide["image_path"] = str(path)

    return unique_slides


def ocr_slides(
    slides: list[dict],
    max_chunk_height: int = 1800,
) -> list[dict]:
    for slide in slides:
        img = slide["image"]
        if img.height > max_chunk_height:
            chunks = []
            for y in range(0, img.height, max_chunk_height - 50):
                chunk = img.crop((0, y, img.width, min(y + max_chunk_height, img.height)))
                chunks.append(call_glm_ocr(chunk, "Text Recognition:"))
            slide["ocr_text"] = "\n".join(chunks)
        else:
            slide["ocr_text"] = call_glm_ocr(img, "Text Recognition:")
    return slides


def detect_code_changes(
    clip_frames: dict[int, list[Image.Image]],
    diff_threshold: float = 0.03,
) -> list[int]:
    """
    Detect clips where code content changed.
    Returns list of clip indices where changes were detected.
    """
    sorted_indices = sorted(clip_frames.keys())
    change_points = []

    if not sorted_indices:
        return change_points

    change_points.append(sorted_indices[0])

    for i in range(1, len(sorted_indices)):
        prev_idx = sorted_indices[i - 1]
        curr_idx = sorted_indices[i]

        prev_frames = clip_frames[prev_idx]
        curr_frames = clip_frames[curr_idx]

        if not prev_frames or not curr_frames:
            continue

        prev_mid = np.array(prev_frames[len(prev_frames) // 2].convert("L"))
        curr_mid = np.array(curr_frames[len(curr_frames) // 2].convert("L"))

        if prev_mid.shape != curr_mid.shape:
            change_points.append(curr_idx)
            continue

        diff = np.abs(prev_mid.astype(np.int16) - curr_mid.astype(np.int16))
        change_ratio = (diff > 20).mean()

        if change_ratio > diff_threshold:
            change_points.append(curr_idx)

    return change_points


def extract_code_snapshots(
    clip_frames: dict[int, list[Image.Image]],
    change_points: list[int],
) -> list[dict]:
    """
    Extract code text at each change point, dedup by code content hash.
    """
    seen_code_hashes = set()
    snapshots = []

    for clip_idx in change_points:
        frames = clip_frames.get(clip_idx, [])
        if not frames:
            continue

        mid_frame = frames[len(frames) // 2]
        code_text = _ocr_code_frame(mid_frame, "Text Recognition: 请识别图片中所有代码，保持原始格式和缩进。")

        if not code_text or len(code_text) < 20:
            continue

        # whole text: a clean OCR starts every snapshot with the same menu bar, so a prefix hash
        # would keep only the first snapshot
        code_hash = hash(code_text)
        if code_hash in seen_code_hashes:
            continue
        seen_code_hashes.add(code_hash)

        snapshots.append({
            "clip_idx": clip_idx,
            "time": 0.0,
            "code": code_text,
            "image": mid_frame,
        })

    return snapshots
