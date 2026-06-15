# coding=utf-8
import numpy as np
from PIL import Image
import cv2
from pathlib import Path
from external_api import call_glm_ocr


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


def extract_unique_slides(
    clip_frames: dict[int, list[Image.Image]],
    clip_captions: dict[int, str],
    hash_threshold: int = 8,
    min_change_ratio: float = 0.02,
    output_dir: str | None = None,
) -> list[dict]:
    """
    Extract unique slides from video clips.

    Args:
        clip_frames: {clip_idx: [PIL.Image, ...]}
        clip_captions: {clip_idx: "caption text"}
        hash_threshold: pHash distance threshold for slide dedup
        min_change_ratio: minimum pixel change ratio to consider a new slide
        output_dir: if set, save slide images to this directory

    Returns:
        list of {"time": float, "image": PIL.Image, "clip_idx": int, "phash": str}
    """
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    unique_slides = []
    seen_hashes = []

    for clip_idx in sorted(clip_frames.keys()):
        frames = clip_frames[clip_idx]
        if not frames:
            continue

        best_frame = _pick_best_frame(frames)

        if _is_low_quality(best_frame):
            continue

        h = _compute_phash(best_frame)

        is_dup = False
        for seen_h in seen_hashes:
            if _hash_distance(h, seen_h) <= hash_threshold:
                is_dup = True
                break

        if not is_dup:
            seen_hashes.append(h)
            entry = {
                "clip_idx": clip_idx,
                "time": 0.0,
                "image": best_frame,
                "phash": f"{h:016x}",
            }
            unique_slides.append(entry)

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
    code_hash_size: int = 64,
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
        code_text = call_glm_ocr(mid_frame, "Text Recognition: 请识别图片中所有代码，保持原始格式和缩进。")

        if not code_text or len(code_text) < 20:
            continue

        code_hash = hash(code_text[:code_hash_size])
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
