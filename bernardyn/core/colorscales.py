"""Continuous color scales sampled to N evenly spaced series colors.

Unlike a fixed palette that recycles, a scale always spans its full range from
first to last series, so the step between neighbours shrinks as N grows.
Pure Python: no numpy, Qt or matplotlib.
"""

from __future__ import annotations

import colorsys

Color = tuple[int, int, int, int]

# Anchor colors (hex) interpolated linearly in RGB. Values follow the widely used
# Turbo (Google), Spectral (ColorBrewer, reversed to run red -> blue) and Viridis maps.
_ANCHORS: dict[str, tuple[str, ...]] = {
    "turbo": (
        "30123b", "4662d7", "36aaf9", "1ae4b6", "72fe5e",
        "c7ef34", "faba39", "f66b19", "7a0403",
    ),
    "spectral": (
        "d53e4f", "f46d43", "fdae61", "fee08b", "e6f598",
        "abdda4", "66c2a5", "3288bd", "5e4fa2",
    ),
    "viridis": ("440154", "3b528b", "21908d", "5dc863", "fde725"),
}

# Menu label for each scale key, in menu order.
COLOR_SCALES: dict[str, str] = {
    "rainbow": "Rainbow (red to violet)",
    "turbo": "Turbo (blue to red)",
    "spectral": "Spectral (red to violet, soft)",
    "viridis": "Viridis (purple to yellow)",
}


def _hex_rgb(value: str) -> tuple[int, int, int]:
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def scale_color(name: str, t: float) -> Color:
    """Return the RGBA color of scale ``name`` at position ``t`` in [0, 1]."""
    t = min(1.0, max(0.0, t))
    if name == "rainbow":
        # Hue 0 deg (red) to 270 deg (violet); stopping short of 360 keeps the
        # last color distinct from the first.
        r, g, b = colorsys.hsv_to_rgb(0.75 * t, 1.0, 0.9)
        return round(r * 255), round(g * 255), round(b * 255), 255
    anchors = _ANCHORS[name]
    pos = t * (len(anchors) - 1)
    lo = min(int(pos), len(anchors) - 2)
    frac = pos - lo
    a, b = _hex_rgb(anchors[lo]), _hex_rgb(anchors[lo + 1])
    r, g, bl = (round(a[i] + (b[i] - a[i]) * frac) for i in range(3))
    return r, g, bl, 255


def sample_scale(name: str, count: int) -> list[Color]:
    """Return ``count`` colors evenly spaced over the whole scale ``name``."""
    if name not in COLOR_SCALES:
        raise ValueError(f"Unknown color scale: {name}")
    if count <= 0:
        return []
    if count == 1:
        return [scale_color(name, 0.0)]
    return [scale_color(name, i / (count - 1)) for i in range(count)]
