import colorsys
import random


TAG_COLOR_PRESETS = [
    "#3B82F6",
    "#14B8A6",
    "#10B981",
    "#84CC16",
    "#F59E0B",
    "#F97316",
    "#EF4444",
    "#EC4899",
    "#8B5CF6",
    "#6366F1",
    "#06B6D4",
    "#64748B",
]

SOFT_SATURATION_STEPS = (0.58, 0.62, 0.56)
SOFT_LIGHTNESS_STEPS = (0.48, 0.52, 0.5)
AVOID_HUE_RANGES = (
    (0.11, 0.18),  # skip the brightest yellow-green band
)


def _normalize_color(color: str) -> str:
    return (color or "").strip().upper()


def _hsl_to_hex(hue: float, saturation: float = 0.72, lightness: float = 0.56) -> str:
    r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def _is_avoided_hue(hue: float) -> bool:
    return any(start <= hue <= end for start, end in AVOID_HUE_RANGES)


def _generate_extended_color(existing_colors: set[str]) -> str:
    normalized_existing = {_normalize_color(color) for color in existing_colors}
    attempts = len(normalized_existing)
    while True:
        hue = ((attempts * 137.508) % 360) / 360.0
        if _is_avoided_hue(hue):
            attempts += 1
            continue
        saturation = SOFT_SATURATION_STEPS[attempts % len(SOFT_SATURATION_STEPS)]
        lightness = SOFT_LIGHTNESS_STEPS[attempts % len(SOFT_LIGHTNESS_STEPS)]
        color = _hsl_to_hex(hue, saturation=saturation, lightness=lightness)
        if color not in normalized_existing:
            return color
        attempts += 1


def get_distinct_tag_color(existing_colors=None, prefer_random: bool = True) -> str:
    existing_colors = existing_colors or []
    normalized_existing = {_normalize_color(color) for color in existing_colors}
    available_presets = [
        color for color in TAG_COLOR_PRESETS if _normalize_color(color) not in normalized_existing
    ]
    if available_presets:
        if prefer_random:
            return random.choice(available_presets)
        return available_presets[0]
    return _generate_extended_color(normalized_existing)


def get_random_tag_color(existing_colors=None) -> str:
    return get_distinct_tag_color(existing_colors=existing_colors, prefer_random=True)
