import pytest

from kami.geometry import Rect, fit_inside, layer_rect, scaled_size, to_point

SCREEN = Rect(0, 0, 1920, 1080)


def test_layer_inside_screen_keeps_padding():
    layer, inner = layer_rect(Rect(500, 400, 200, 100), SCREEN, 60)
    assert layer == Rect(440, 340, 320, 220)
    assert inner == Rect(60, 60, 200, 100)


@pytest.mark.parametrize("region", [
    Rect(0, 400, 200, 100),        # left edge
    Rect(1720, 400, 200, 100),     # right edge
    Rect(500, 0, 200, 100),        # top edge
    Rect(500, 980, 200, 100),      # bottom edge
    Rect(10, 10, 1900, 1060),      # nearly the whole screen
])
def test_layer_clipped_at_each_edge(region):
    layer, inner = layer_rect(region, SCREEN, 60)
    assert layer.x >= SCREEN.x and layer.y >= SCREEN.y
    assert layer.right <= SCREEN.right and layer.bottom <= SCREEN.bottom
    # the region is still exactly where it was on screen
    assert (layer.x + inner.x, layer.y + inner.y) == (region.x, region.y)
    assert (inner.w, inner.h) == (region.w, region.h)


def test_layer_on_negative_coordinates():
    left_screen = Rect(-1920, 0, 1920, 1080)
    layer, inner = layer_rect(Rect(-1920, 500, 300, 200), left_screen, 60)
    assert layer.x == -1920
    assert layer.right == -1920 + 300 + 60
    assert (layer.x + inner.x, layer.y + inner.y) == (-1920, 500)


def test_to_point_corners():
    inner = Rect(60, 40, 200, 100)
    assert to_point(inner, 0, 0) == (60, 40)
    assert to_point(inner, 1, 1) == (260, 140)
    assert to_point(inner, 0.5, 0.5) == (160, 90)


@pytest.mark.parametrize("box, expected", [
    (Rect(-30, 10, 100, 20), Rect(0, 10, 100, 20)),
    (Rect(1900, 10, 100, 20), Rect(1820, 10, 100, 20)),
    (Rect(10, -5, 100, 20), Rect(10, 0, 100, 20)),
    (Rect(10, 1075, 100, 20), Rect(10, 1060, 100, 20)),
    (Rect(50, 50, 100, 20), Rect(50, 50, 100, 20)),
])
def test_fit_inside_moves_not_resizes(box, expected):
    assert fit_inside(box, SCREEN) == expected


def test_fit_inside_too_big_pins_top_left():
    assert fit_inside(Rect(-50, -50, 3000, 2000), SCREEN) == Rect(0, 0, 3000, 2000)


def test_scaled_size():
    assert scaled_size(3000, 1000, 1568) == (1568, 523)
    assert scaled_size(1000, 3000, 1568) == (523, 1568)
    assert scaled_size(800, 600, 1568) == (800, 600)
    assert scaled_size(1568, 10, 1568) == (1568, 10)
    assert scaled_size(100_000, 1, 1568) == (1568, 1)
