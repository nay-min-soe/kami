# Task 7 — Annotation polish

**Size:** S · **Depends on:** Task 6 (`geometry.fit_inside`, screen-clipped layer) · **Branch:** `doodle-polish`

## Goal

Doodles fade out gently, you can keep them on screen while you work, and labels are
always readable: on screen, not on top of each other.

## Current state

- `AnnotationLayer` hides abruptly after 25 s (`hide_after_ms`).
- There's no way to keep doodles longer than 25 s. **Clear doodles** is the only control.
- `_note` keeps a label inside the layer window, but (until Task 6) that window can
  extend off-screen. Labels can overlap each other, and long labels aren't shortened.

## Design

- **Fade out:** over the last 600 ms, animate `windowOpacity` from 1 to 0 with
  `QPropertyAnimation`, then `clear()`. Without a compositor, X11 ignores window
  opacity, so the doodles simply disappear at the end, the same as today. That's fine.
- **Keep doodles:** a checkable **📌 Keep** button in the panel. When it's on, the
  hide timer doesn't run. Turning it off starts the 25 s countdown again.
  **Clear doodles** always clears. The setting lasts for the session only, with no
  config key (smallest version first; add one later if people ask).
- **Label placement:** a pure function in `geometry.py`:
  ```python
  def place_label(anchor: tuple[float, float], size: tuple[float, float],
                  bounds: Rect, taken: list[Rect]) -> Rect:
  ```
  Try 4 spots around the anchor (right-above, right-below, left-above, left-below).
  Take the first that fits inside `bounds` and doesn't overlap a label in `taken`.
  If none works, use `fit_inside` on the first spot. `paintEvent` places labels in
  order and passes the boxes already used.
- **Long labels:** shorten with `QFontMetrics.elidedText(..., Qt.ElideRight, 220)`.
  The parser already caps labels at 60 characters (Task 1).

## Files

| File | Change |
|---|---|
| `src/kami/geometry.py` | `place_label` |
| `src/kami/ui/annotation.py` | fade animation, keep mode, use `place_label`, elide |
| `src/kami/ui/overlay.py` | 📌 Keep toggle |
| `tests/test_geometry.py` | `place_label` cases |
| `README.md` | mention Keep + fade in the Explain screen row |

## Tests — add to `tests/test_geometry.py`

- [x] `test_place_label_prefers_right_above`: plenty of room → right-above spot
- [x] `test_place_label_flips_at_right_edge`: an anchor near the right edge → a left-side spot inside the bounds
- [x] `test_place_label_flips_at_top_edge`: an anchor at the top → a below spot
- [x] `test_place_label_avoids_taken`: when right-above overlaps a taken box, the next free spot is used
- [x] `test_place_label_always_inside_bounds`: a crowded case with no free spot is still inside the bounds

## Manual check (X11, `KAMI_DEBUG_DOODLES=1` from Task 6 works well here)

- [ ] Doodles fade over about half a second at 25 s instead of vanishing (with a compositor)
- [ ] With 📌 Keep on, doodles stay past 25 s, and Clear doodles still removes them
- [ ] A region in the top-right corner of the screen: every label is fully visible
- [ ] Two circles close together: their labels don't overlap

## Done when

- [ ] Labels never leave the screen and don't overlap in the tested cases
- [ ] Keep and fade work as above

## Commits

1. `place doodle labels inside the screen`
2. `fade doodles out and add keep toggle`
