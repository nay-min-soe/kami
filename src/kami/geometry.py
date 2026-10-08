"""Screen maths for the doodle layer and captures. No Qt, so pytest covers it.

All rects are in pixels with the origin at the top-left; screens can sit at negative
coordinates (a monitor left of or above the primary one).
"""
from __future__ import annotations

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
