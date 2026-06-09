# coding=utf-8
"""Perspective correction for tilted/skewed screenshots and photos."""
import cv2
import numpy as np
from PIL import Image

from external_api import call_vision_for_corners, _pil_to_base64

_RECT_DEVIATION_THRESHOLD = 1.5
_MIN_AREA_RATIO = 0.15


def needs_correction(image: Image.Image) -> bool:
    """Quick CV check: is the main content area non-rectangular?"""
    arr = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape

    edges = cv2.Canny(gray, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3)), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return False

    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    if area < h * w * _MIN_AREA_RATIO:
        return False

    approx = cv2.approxPolyDP(largest, 0.02 * cv2.arcLength(largest, True), True)
    if len(approx) != 4:
        return len(approx) > 4

    pts = approx.reshape(4, 2).astype(np.float32)
    angles = []
    for i in range(4):
        p1 = pts[i]
        p2 = pts[(i + 1) % 4]
        p3 = pts[(i + 2) % 4]
        v1 = p1 - p2
        v2 = p3 - p2
        cos_a = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-8)
        angles.append(np.degrees(np.arccos(np.clip(cos_a, -1, 1))))

    return any(abs(a - 90) > _RECT_DEVIATION_THRESHOLD for a in angles)


def detect_corners(image: Image.Image, provider: str = "gemini") -> np.ndarray | None:
    """Use a vision model to detect the 4 corner points of the main content.

    Returns (4,2) float32 array [TL, TR, BR, BL] or None.
    """
    w, h = image.size
    b64 = _pil_to_base64(image)
    corners = call_vision_for_corners(b64, w, h, provider=provider)
    if corners is None:
        return None

    order = ("top_left", "top_right", "bottom_right", "bottom_left")
    pts = np.array([[corners[k]["x"], corners[k]["y"]] for k in order], dtype=np.float32)

    if _is_degenerate(pts, w, h):
        return None
    return pts


def correct_perspective(image: Image.Image, corners: np.ndarray,
                        target_width: int | None = None,
                        target_height: int | None = None) -> Image.Image:
    """Warp image so the 4 corner points map to a rectangle.

    corners: (4,2) float32 array [TL, TR, BR, BL].
    """
    tl, tr, br, bl = corners

    w_top = np.linalg.norm(tr - tl)
    w_bot = np.linalg.norm(br - bl)
    h_left = np.linalg.norm(bl - tl)
    h_right = np.linalg.norm(br - tr)

    dst_w = target_width or int(max(w_top, w_bot))
    dst_h = target_height or int(max(h_left, h_right))

    dst = np.array([
        [0, 0],
        [dst_w - 1, 0],
        [dst_w - 1, dst_h - 1],
        [0, dst_h - 1],
    ], dtype=np.float32)

    M = cv2.getPerspectiveTransform(corners, dst)
    arr = np.array(image.convert("RGB"))
    warped = cv2.warpPerspective(arr, M, (dst_w, dst_h), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REPLICATE)
    return Image.fromarray(warped)


def auto_correct(image: Image.Image, force: bool = False,
                 provider: str = "gemini") -> Image.Image:
    """Detect if image needs perspective correction and apply it.

    Set force=True to skip the CV pre-check and always use vision model.
    """
    if not force and not needs_correction(image):
        return image

    corners = detect_corners(image, provider=provider)
    if corners is None:
        return image

    if not _rectify_corners(corners):
        return image

    return correct_perspective(image, corners)


def _is_degenerate(pts: np.ndarray, img_w: int, img_h: int) -> bool:
    """Check if detected corners are degenerate (too small or outside image)."""
    xs, ys = pts[:, 0], pts[:, 1]
    margin_x, margin_y = img_w * 0.02, img_h * 0.02
    if any(x < -margin_x or x > img_w + margin_x for x in xs):
        return True
    if any(y < -margin_y or y > img_h + margin_y for y in ys):
        return True

    area = cv2.contourArea(pts.reshape(1, 4, 2).astype(np.float32))
    return area < img_w * img_h * _MIN_AREA_RATIO


def _rectify_corners(pts: np.ndarray) -> bool:
    """Check if the 4 corners actually form a non-rectangle that needs correction."""
    for i in range(4):
        p1 = pts[i]
        p2 = pts[(i + 1) % 4]
        p3 = pts[(i + 2) % 4]
        v1 = p1 - p2
        v2 = p3 - p2
        cos_a = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-8)
        angle = np.degrees(np.arccos(np.clip(cos_a, -1, 1)))
        if abs(angle - 90) > _RECT_DEVIATION_THRESHOLD:
            return True
    return False
