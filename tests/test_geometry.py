import pytest

from kami.geometry import (
    Rect,
    crop_rect,
    fit_inside,
    layer_rect,
    overlaps,
    place_label,
    scaled_size,
    to_point,
)

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


LABEL = (100, 20)


def test_place_label_prefers_right_above():
    assert place_label((500, 500), LABEL, SCREEN, []) == Rect(500, 480, 100, 20)


def test_place_label_flips_at_right_edge():
    box = place_label((1900, 500), LABEL, SCREEN, [])
    assert box == Rect(1800, 480, 100, 20)
    assert box.right <= SCREEN.right


def test_place_label_flips_at_top_edge():
    assert place_label((500, 5), LABEL, SCREEN, []) == Rect(500, 5, 100, 20)


def test_place_label_flips_at_top_right_corner():
    assert place_label((1900, 5), LABEL, SCREEN, []) == Rect(1800, 5, 100, 20)


def test_place_label_avoids_taken():
    first = place_label((500, 500), LABEL, SCREEN, [])
    second = place_label((510, 505), LABEL, SCREEN, [first])
    assert not overlaps(first, second)
    assert second == Rect(510, 505, 100, 20)   # right-below


def test_place_label_always_inside_bounds():
    small = Rect(0, 0, 150, 30)
    taken = [Rect(0, 0, 150, 30)]          # nothing is free
    box = place_label((140, 25), LABEL, small, taken)
    assert fit_inside(box, small) == box


def test_overlaps_ignores_touching_edges():
    assert not overlaps(Rect(0, 0, 10, 10), Rect(10, 0, 10, 10))
    assert overlaps(Rect(0, 0, 10, 10), Rect(9, 9, 10, 10))


def test_place_label_crowded_corner_stacks_without_overlap():
    taken: list[Rect] = []
    for _ in range(3):
        taken.append(place_label((1900, 5), LABEL, SCREEN, taken))
    assert all(fit_inside(b, SCREEN) == b for b in taken)
    assert not any(overlaps(a, b) for i, a in enumerate(taken) for b in taken[i + 1:])


# crop_rect: Qt logical global coordinates -> pixels in the portal's screenshot.

def _inside(crop: Rect, w: int, h: int) -> bool:
    return 0 <= crop.x and 0 <= crop.y and crop.right <= w and crop.bottom <= h


def _whole(crop: Rect) -> bool:
    return all(float(v).is_integer() for v in (crop.x, crop.y, crop.w, crop.h))


def test_crop_single_screen_100():
    crop = crop_rect(Rect(100, 200, 300, 150), [SCREEN], 1920, 1080)
    assert crop == Rect(100, 200, 300, 150)
    assert _whole(crop)


def test_crop_single_screen_200():
    crop = crop_rect(Rect(100, 200, 300, 150), [SCREEN], 3840, 2160)
    assert crop == Rect(200, 400, 600, 300)


def test_crop_fractional_125():
    # 1536x864 logical at 125 % -> 1920x1080 pixels. 101 * 1.25 = 126.25 and
    # 51 * 1.25 = 63.75: the edges go outward, never inward.
    crop = crop_rect(Rect(101, 51, 101, 51), [Rect(0, 0, 1536, 864)], 1920, 1080)
    assert crop == Rect(126, 63, 127, 65)    # x 126.25..252.5, y 63.75..127.5
    assert _whole(crop)


def test_crop_exact_multiples_have_no_float_creep():
    # k = 1.1: 100 * 1.1 is 110.00000000000001 in floats, which must not ceil to 111.
    crop = crop_rect(Rect(50, 50, 50, 50), [Rect(0, 0, 1000, 1000)], 1100, 1100)
    assert crop == Rect(55, 55, 55, 55)


TWO = [Rect(0, 0, 1920, 1080), Rect(1920, 0, 1920, 1080)]


def test_crop_second_screen():
    crop = crop_rect(Rect(2000, 100, 400, 300), TWO, 3840, 1080)
    assert crop == Rect(2000, 100, 400, 300)


def test_crop_whole_screen_of_two():
    assert crop_rect(TWO[1], TWO, 3840, 1080) == Rect(1920, 0, 1920, 1080)
    assert crop_rect(TWO[0], TWO, 3840, 1080) == Rect(0, 0, 1920, 1080)


def test_crop_negative_origin():
    screens = [Rect(-1920, 0, 1920, 1080), Rect(0, 0, 1920, 1080)]
    assert crop_rect(Rect(-1820, 100, 200, 100), screens, 3840, 1080) == Rect(100, 100, 200, 100)
    assert crop_rect(screens[1], screens, 3840, 1080) == Rect(1920, 0, 1920, 1080)


@pytest.mark.parametrize("region", [
    Rect(1800, 1000, 500, 500),     # past the bottom-right corner
    Rect(-300, -300, 500, 500),     # past the top-left corner
    Rect(-10, -10, 5000, 5000),     # bigger than everything
])
def test_crop_clamped_to_image(region):
    crop = crop_rect(region, [SCREEN], 1920, 1080)
    assert crop is not None
    assert _inside(crop, 1920, 1080)
    assert _whole(crop)


def test_crop_fully_outside_is_none():
    assert crop_rect(Rect(5000, 5000, 100, 100), [SCREEN], 1920, 1080) is None


@pytest.mark.parametrize("region", [Rect(10, 10, 0, 50), Rect(10, 10, 50, 0),
                                    Rect(10, 10, -5, 50)])
def test_crop_empty_region_is_none(region):
    assert crop_rect(region, [SCREEN], 1920, 1080) is None


def test_crop_layout_mismatch_is_none():
    # A 1080-high image can't be one 1920x1200 screen at k = 1.
    assert crop_rect(Rect(0, 0, 100, 100), [Rect(0, 0, 1920, 1200)], 1920, 1080) is None
    # The offscreen 800x800 screen with a 1920x1080 image (the manual check's trap).
    assert crop_rect(Rect(0, 0, 100, 100), [Rect(0, 0, 800, 800)], 1920, 1080) is None


def test_crop_height_tolerance():
    # Off by 2 px (or 1 % of the height) still lines up; more doesn't.
    assert crop_rect(Rect(0, 0, 10, 10), [SCREEN], 1920, 1082) is not None
    assert crop_rect(Rect(0, 0, 10, 10), [SCREEN], 1920, 1092) is None


def test_crop_no_screens_is_none():
    assert crop_rect(Rect(0, 0, 100, 100), [], 1920, 1080) is None


@pytest.mark.parametrize("w, h", [(0, 1080), (1920, 0), (-1920, 1080)])
def test_crop_empty_image_is_none(w, h):
    assert crop_rect(Rect(0, 0, 100, 100), [SCREEN], w, h) is None


def test_crop_zero_size_screen_is_none():
    assert crop_rect(Rect(0, 0, 100, 100), [Rect(0, 0, 0, 0)], 1920, 1080) is None
