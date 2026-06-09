# coding=utf-8
"""
Pure numpy+PIL image preprocessing for MiniCPM-V, replacing transformers AutoProcessor.

Eliminates torch runtime dependency. V4.5 and V4.6 supported.

Usage:
    from preprocess import preprocess_image, preprocess_frame
    tiles = preprocess_image(pil_image, version="4.6")
    tiles = preprocess_frame(pil_image, version="4.5")
"""
import math
import numpy as np
from PIL import Image


PATCH_SIZE = 14
MEAN = np.array([0.5, 0.5, 0.5], dtype=np.float32)
STD = np.array([0.5, 0.5, 0.5], dtype=np.float32)


def _ensure_divide(length, divisor):
    return max(round(length / divisor) * divisor, divisor)


def _find_best_resize(image_size, scale_resolution, patch_size, patch_divisor, allow_upscale=False):
    """Find resize target ensuring dimensions are divisible by patch_divisor.

    Args:
        image_size: (width, height) — PIL convention
        scale_resolution: target pixel count boundary
        patch_size: 14
        patch_divisor: patch_size for V4.5, patch_size*4 for V4.6
        allow_upscale: allow upscaling small images
    Returns:
        (width, height)
    """
    width, height = image_size
    if (width * height > scale_resolution * scale_resolution) or allow_upscale:
        r = width / height
        height = int(scale_resolution / math.sqrt(r))
        width = int(height * r)
    best_width = _ensure_divide(width, patch_divisor)
    best_height = _ensure_divide(height, patch_divisor)
    return best_width, best_height


def _get_refine_size(image_size, grid, scale_resolution, patch_size, patch_divisor,
                     allow_upscale=False, version="4.5"):
    width, height = image_size
    if version == "4.6":
        width_div, height_div = grid[1], grid[0]
    else:
        width_div, height_div = grid[0], grid[1]
    refine_width = _ensure_divide(width, width_div)
    refine_height = _ensure_divide(height, height_div)
    per_tile_w = refine_width / width_div
    per_tile_h = refine_height / height_div
    best_w, best_h = _find_best_resize(
        (per_tile_w, per_tile_h), scale_resolution, patch_size, patch_divisor, allow_upscale=allow_upscale
    )
    return best_w * width_div, best_h * height_div


def _get_sliced_grid(image_size, max_slice_nums, scale_resolution, version="4.5"):
    original_width, original_height = image_size
    log_ratio = math.log(original_width / original_height)
    ratio = original_width * original_height / (scale_resolution * scale_resolution)
    multiple = min(math.ceil(ratio), max_slice_nums)
    if multiple <= 1:
        return None

    best_grid = [1, 1]
    min_error = float("inf")

    if version == "4.5":
        # V4.5 generates [m, split//m] where m=rows -> [rows, cols]
        candidate_split_grids_nums = []
        for i in [multiple - 1, multiple, multiple + 1]:
            if i == 1 or i > max_slice_nums:
                continue
            candidate_split_grids_nums.append(i)
        candidate_grids = []
        for n in candidate_split_grids_nums:
            m = 1
            while m <= n:
                if n % m == 0:
                    candidate_grids.append([m, n // m])
                m += 1
        for grid in candidate_grids:
            error = abs(log_ratio - math.log(grid[0] / grid[1]))
            if error < min_error:
                best_grid = grid
                min_error = error
    else:
        # V4.6 generates [num_cols, num_rows]
        for num_slices in [multiple - 1, multiple, multiple + 1]:
            if num_slices == 1 or num_slices > max_slice_nums:
                continue
            for num_rows in range(1, num_slices + 1):
                if num_slices % num_rows == 0:
                    num_cols = num_slices // num_rows
                    error = abs(log_ratio - math.log(num_rows / num_cols))
                    if error < min_error:
                        best_grid = [num_cols, num_rows]
                        min_error = error

    return best_grid


def _split_to_patches(image, grid, version="4.5"):
    width, height = image.size
    if version == "4.6":
        width_div, height_div = grid[1], grid[0]
    else:
        width_div, height_div = grid[0], grid[1]
    patch_w = width // width_div
    patch_h = height // height_div
    patches = []
    for i in range(0, height, patch_h):
        row = []
        for j in range(0, width, patch_w):
            row.append(image.crop((j, i, j + patch_w, i + patch_h)))
        patches.append(row)
    return patches


def _get_sliced_images(image, max_slice_nums, scale_resolution, patch_size, patch_divisor, version="4.5"):
    original_size = image.size
    best_grid = _get_sliced_grid(original_size, max_slice_nums, scale_resolution, version=version)
    source_image = None
    slice_patches = []

    if best_grid is None:
        best_size = _find_best_resize(original_size, scale_resolution, patch_size, patch_divisor, allow_upscale=True)
        source_image = image.resize(best_size, resample=Image.Resampling.BICUBIC)
    else:
        best_resize = _find_best_resize(original_size, scale_resolution, patch_size, patch_divisor)
        source_image = image.copy().resize(best_resize, resample=Image.Resampling.BICUBIC)
        refine_size = _get_refine_size(
            original_size, best_grid, scale_resolution, patch_size, patch_divisor,
            allow_upscale=True, version=version
        )
        refine_image = image.resize(refine_size, resample=Image.Resampling.BICUBIC)
        slice_patches = _split_to_patches(refine_image, best_grid, version=version)

    images = [source_image]
    for row in slice_patches:
        images.extend(row)
    return images


def _normalize_image(img_array):
    """Normalize [H, W, 3] uint8 array to [3, H, W] float32 in range [-1, 1]."""
    x = img_array.astype(np.float32) / 255.0
    x = (x - MEAN) / STD
    return x.transpose(2, 0, 1)


def _reshape_by_patch(image, patch_size):
    """Replicate torch.nn.functional.unfold + reshape for non-overlapping patches.

    Args:
        image: [C, H, W] float32 array
        patch_size: 14
    Returns:
        [C, patch_size, H*W/patch_size]
    """
    C, H, W = image.shape
    ps = patch_size
    ph = H // ps
    pw = W // ps
    x = image.reshape(C, ph, ps, pw, ps)
    x = x.transpose(0, 2, 4, 1, 3).reshape(C, ps, ps, ph * pw)
    x = x.transpose(0, 1, 3, 2).reshape(C, ps, ph * pw * ps)
    return x


def _process_tile(pil_tile, patch_size):
    """Convert a PIL tile to NaViT patchified format.

    Returns:
        pixel_values: [3, patch_size, total_patch_pixels] float32
        h: patch grid height
        w: patch grid width
    """
    arr = np.array(pil_tile)
    x = _normalize_image(arr)
    h = x.shape[1] // patch_size
    w = x.shape[2] // patch_size
    pv = _reshape_by_patch(x, patch_size)
    return pv, h, w


def preprocess_image(image, version="4.6", max_slice_nums=9, scale_resolution=448):
    """Preprocess a single PIL Image into tiles for ONNX encoding.

    Args:
        image: PIL.Image.Image (RGB)
        version: "4.5" or "4.6"
        max_slice_nums: max number of slice tiles (default 9)
        scale_resolution: target resolution for slices (default 448)
    Returns:
        list of dicts, each with:
            "pixel_values": numpy array [1, 3, 14, total_patch_pixels]
            "h": patch grid height (int)
            "w": patch grid width (int)
    """
    patch_divisor = PATCH_SIZE * 4 if version == "4.6" else PATCH_SIZE

    if not isinstance(image, Image.Image):
        raise TypeError("Expected PIL.Image.Image")
    image = image.convert("RGB")

    tiles_pil = _get_sliced_images(image, max_slice_nums, scale_resolution, PATCH_SIZE, patch_divisor, version=version)

    result = []
    all_pv = []
    all_hw = []
    for tile in tiles_pil:
        pv, h, w = _process_tile(tile, PATCH_SIZE)
        all_pv.append(pv)
        all_hw.append((h, w))

    if version == "4.6":
        packed = np.concatenate(all_pv, axis=-1)
        offset = 0
        for pv, (h, w) in zip(all_pv, all_hw):
            tile_px = h * w * PATCH_SIZE
            result.append({
                "pixel_values": packed[np.newaxis, :, :, offset:offset + tile_px].astype(np.float32),
                "h": h,
                "w": w,
            })
            offset += tile_px
    else:
        for pv, (h, w) in zip(all_pv, all_hw):
            result.append({
                "pixel_values": pv[np.newaxis].astype(np.float32),
                "h": h,
                "w": w,
            })

    return result


def preprocess_frame(frame, frame_idx=0, version="4.5", max_slice_nums=9, scale_resolution=448):
    """Preprocess a single video frame into tiles with frame index metadata.

    Returns:
        list of dicts with pixel_values, h, w, frame
    """
    tiles = preprocess_image(frame, version, max_slice_nums, scale_resolution)
    for t in tiles:
        t["frame"] = frame_idx
    return tiles


def extract_frames(video_path, num_frames=8):
    """Extract evenly spaced frames from a video file."""
    import av
    container = av.open(video_path)
    stream = container.streams.video[0]
    total = stream.frames
    indices = np.linspace(0, total - 1, num_frames, dtype=int)
    frames = []
    for i, frame in enumerate(container.decode(stream)):
        if len(frames) >= num_frames:
            break
        if i >= indices[len(frames)]:
            frames.append(frame.to_image())
    container.close()
    return frames


# ---------------------------------------------------------------------------
# Temporal position embedding (1D sin-cos, matches resampler.py)
# ---------------------------------------------------------------------------

def get_1d_sincos_pos_embed_from_temporal(embed_dim, positions):
    """Compute 1D sinusoidal positional embeddings for temporal positions.

    Args:
        embed_dim: output dimension (must be even), e.g. 4096 for V4.5 Resampler
        positions: 1D array of temporal indices, shape (M,)
    Returns:
        embeddings: (M, embed_dim) float32
    """
    assert embed_dim % 2 == 0
    positions = np.asarray(positions, dtype=np.float32).reshape(-1)
    omega = np.arange(embed_dim // 2, dtype=np.float32)
    omega = 1.0 / (10000 ** (omega / (embed_dim / 2)))  # (D/2,)
    out = np.einsum('m,d->md', positions, omega)  # (M, D/2)
    emb = np.concatenate([np.sin(out), np.cos(out)], axis=1)  # (M, D)
    return emb.astype(np.float32)


def compute_temporal_embeddings_for_group(frame_count, temporal_ids_group, embed_dim):
    """Compute per-patch temporal embeddings for a temporal group.

    For each frame in the group, its temporal embedding is repeated for all
    its patches, then all frames' patches are concatenated.

    Args:
        frame_count: list of patch counts per frame, e.g. [1024, 1024, 1024]
        temporal_ids_group: list of temporal IDs, one per frame, e.g. [0, 3, 6]
        embed_dim: embedding dimension (4096 for V4.5)
    Returns:
        temporal_embeds: (sum(frame_count), embed_dim) float32
    """
    temporal_emb = get_1d_sincos_pos_embed_from_temporal(embed_dim, temporal_ids_group)
    # temporal_emb: (num_frames, embed_dim)
    # Repeat each frame's embedding for all its patches
    parts = []
    for i, n_patches in enumerate(frame_count):
        parts.append(np.tile(temporal_emb[i], (n_patches, 1)))  # (n_patches, embed_dim)
    return np.concatenate(parts, axis=0)


def encode_video_temporal_ids(frame_indices, fps, time_scale=0.1):
    """Convert frame indices to temporal IDs (time-quantized).

    Matches the official MiniCPM-V 4.5 encode_video logic.

    Args:
        frame_indices: array of frame indices in the video
        fps: video FPS
        time_scale: quantization step in seconds (default 0.1)
    Returns:
        temporal_ids: list of int temporal IDs
    """
    frame_indices = np.asarray(frame_indices, dtype=np.float64)
    timestamps = frame_indices / fps
    temporal_ids = (np.round(timestamps / time_scale)).astype(np.int32).tolist()
    return temporal_ids


def group_temporal_ids(temporal_ids, packing_size):
    """Split temporal_ids into groups of packing_size.

    Args:
        temporal_ids: flat list of temporal IDs
        packing_size: number of frames per group (1-6)
    Returns:
        grouped: list of lists, e.g. [[t0, t1], [t2, t3], ...]
    """
    return [temporal_ids[i:i + packing_size] for i in range(0, len(temporal_ids), packing_size)]


def get_2d_sincos_pos_embed_numpy(embed_dim, image_size):
    """Compute 2D sinusoidal positional embeddings (matches resampler.py).

    Args:
        embed_dim: output dimension (must be even)
        image_size: (h, w) or int
    Returns:
        pos_embed: (h, w, embed_dim) float32
    """
    if isinstance(image_size, int):
        grid_h_size, grid_w_size = image_size, image_size
    else:
        grid_h_size, grid_w_size = image_size

    grid_h = np.arange(grid_h_size, dtype=np.float32)
    grid_w = np.arange(grid_w_size, dtype=np.float32)
    grid = np.meshgrid(grid_w, grid_h)
    grid = np.stack(grid, axis=0)

    assert embed_dim % 2 == 0
    half = embed_dim // 2

    # h dim
    omega_h = np.arange(half // 2, dtype=np.float32)
    omega_h = 1.0 / (10000 ** (omega_h / (half / 2)))
    out_h = np.einsum('hw,d->hwd', grid[0], omega_h)
    emb_h = np.concatenate([np.sin(out_h), np.cos(out_h)], axis=-1)

    # w dim
    omega_w = np.arange(half // 2, dtype=np.float32)
    omega_w = 1.0 / (10000 ** (omega_w / (half / 2)))
    out_w = np.einsum('hw,d->hwd', grid[1], omega_w)
    emb_w = np.concatenate([np.sin(out_w), np.cos(out_w)], axis=-1)

    return np.concatenate([emb_h, emb_w], axis=-1).astype(np.float32)
