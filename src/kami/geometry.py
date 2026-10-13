"""Screen maths for the doodle layer and captures. No Qt, so pytest covers it.

All rects are in pixels with the origin at the top-left; screens can sit at negative
coordinates (a monitor left of or above the primary one).
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


def layer_rect(region: Rect, screen: Rect, pad: float) -> tuple[Rect, Rect]:
    """The doodle window around `region`, padded but never past the screen edge
    (window managers push such windows back inside, which shifts every doodle).
    Returns (layer in global coords, region relative to the layer)."""
    left, top = max(screen.x, region.x - pad), max(screen.y, region.y - pad)
    right, bottom = min(screen.right, region.right + pad), min(screen.bottom, region.bottom + pad)
    layer = Rect(left, top, right - left, bottom - top)
    return layer, Rect(region.x - left, region.y - top, region.w, region.h)


def to_point(region_in_layer: Rect, x: float, y: float) -> tuple[float, float]:
    """Normalized (0-1) region coordinates to layer pixels."""
    return region_in_layer.x + x * region_in_layer.w, region_in_layer.y + y * region_in_layer.h


def fit_inside(box: Rect, bounds: Rect) -> Rect:
    """Move (never resize) `box` so it lies inside `bounds`; top-left wins if it can't fit."""
    x = max(bounds.x, min(box.x, bounds.right - box.w))
    y = max(bounds.y, min(box.y, bounds.bottom - box.h))
    return Rect(x, y, box.w, box.h)


def scaled_size(w: int, h: int, max_edge: int) -> tuple[int, int]:
    """Shrink (w, h) so the long edge is at most max_edge, keeping the aspect ratio."""
    long_edge = max(w, h)
    if long_edge <= max_edge:
        return w, h
    scale = max_edge / long_edge
    return max(1, round(w * scale)), max(1, round(h * scale))


def crop_rect(region: Rect, screens: list[Rect], image_w: int, image_h: int) -> Rect | None:
    """Where `region` lies in a screenshot of all `screens`, in whole image pixels.

    `region` and `screens` are Qt logical global coordinates. The image is assumed to
    cover the screens' bounding box at one uniform scale k = image_w / bbox.w (a portal
    screenshot; measured k = 1.000 on one 100 % screen, other layouts not yet). Edges round
    outward and are clamped to the image. Returns None when there are no screens, the
    image height doesn't fit that scale (off by more than max(2 px, 1 %)), or the crop
    is empty.
    """
    if not screens or image_w <= 0 or image_h <= 0:
        return None
    left = min(s.x for s in screens)
    top = min(s.y for s in screens)
    width = max(s.right for s in screens) - left
    height = max(s.bottom for s in screens) - top
    if width <= 0 or height <= 0:
        return None
    k = image_w / width
    if abs(image_h - height * k) > max(2, 0.01 * image_h):
        return None

    def px(value: float, rounding: Callable[[float], int]) -> int:
        # round() first so float noise (100 * 1.1 = 110.00000000000001) can't add a pixel
        return rounding(round(value * k, 6))

    x0 = max(0, px(region.x - left, math.floor))
    y0 = max(0, px(region.y - top, math.floor))
    x1 = min(image_w, px(region.right - left, math.ceil))
    y1 = min(image_h, px(region.bottom - top, math.ceil))
    if x1 <= x0 or y1 <= y0:
        return None
    return Rect(x0, y0, x1 - x0, y1 - y0)


def overlaps(a: Rect, b: Rect) -> bool:
    """True if the rects share area (touching edges don't count)."""
    return a.x < b.right and b.x < a.right and a.y < b.bottom and b.y < a.bottom


def place_label(anchor: tuple[float, float], size: tuple[float, float],
                bounds: Rect, taken: list[Rect]) -> Rect:
    """Where a label box goes: the first of right-above, right-below, left-above,
    left-below the anchor that is inside `bounds` and clear of `taken` labels.
    Crowded? Try those spots moved inside the bounds, then just below a taken label.
    Always returns a box inside the bounds (it may overlap only as a last resort)."""
    (ax, ay), (w, h) = anchor, size
    spots = [Rect(ax, ay - h, w, h), Rect(ax, ay, w, h),
             Rect(ax - w, ay - h, w, h), Rect(ax - w, ay, w, h)]
    moved = [fit_inside(s, bounds) for s in spots]
    below = [fit_inside(Rect(moved[0].x, t.bottom + 2, w, h), bounds)
             for t in sorted(taken, key=lambda r: r.bottom)]
    for spot in [s for s, m in zip(spots, moved, strict=True) if s == m] + moved + below:
        if not any(overlaps(spot, t) for t in taken):
            return spot
    return moved[0]
