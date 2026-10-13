# Task 6 — Multi-monitor and HiDPI

**Size:** M · **Depends on:** — · **Branch:** `multi-monitor-hidpi`

## Goal

On any X11 setup (one or two monitors, 100% to 200% scaling), the capture is the box
you drew, and the doodles land within a few pixels of their target.

## Current state (from reading the code; not yet measured)

- `overlay.summon()` always places the panel on `QGuiApplication.primaryScreen()`, even
  when you're working on the other monitor.
- `RegionSelector.start()` covers only the screen under the cursor. That's fine:
  selecting across two monitors isn't needed. Keep it, and say so in the README.
- `_capture_and_explain` picks the screen at the region's centre and calls
  `screen.grabWindow(0, x, y, w, h)` in logical (scaled) coordinates. How Qt maps this
  to physical pixels at 150% / 200% on X11, and on a screen left of or above the
  primary (negative coordinates), is **unverified**.
- `AnnotationLayer.show_annotations` sets its geometry to the region **plus 60 px
  padding on every side**. Near a screen edge, that window spills onto the next
  monitor or off-screen, and X11 window managers often move such windows back inside
  the screen. That would shift every doodle. This is the most likely cause of offsets.
- At 200%, a 1000×800 box becomes a 2000×1600 PNG. That costs more tokens, especially
  once Task 4 sends the image again with every follow-up.

## Approach: measure first, then fix

1. **Calibration mode.** When `KAMI_DEBUG_DOODLES=1` is set, Explain screen skips the
   model and draws a fixed pattern: small circles at the 4 corners (0,0), (1,0),
   (0,1), (1,1), a cross at (0.5, 0.5), and a text label at each edge. No API call, no
   cost. Measure the offset on each setup in the matrix below by zooming a screenshot.
2. **Pure geometry module**, `src/kami/geometry.py` (no Qt; a small `Rect` dataclass), so
   the maths is tested in CI:
   - `layer_rect(region, screen, pad) -> tuple[Rect, Rect]`: the annotation window
     clipped to the screen, plus where the region sits inside it.
   - `to_point(region_in_layer, x, y) -> tuple[float, float]`: normalized → layer pixels.
   - `fit_inside(box, bounds) -> Rect`: moves a box so it fits on screen (used by Task 7).
   - `scaled_size(w, h, max_edge) -> tuple[int, int]`: keeps the aspect ratio.
3. **Fixes**, applied based on what step 1 shows:
   - The annotation layer uses `layer_rect` (never crosses the screen edge).
   - `summon()` opens on the screen under the cursor.
   - Captures larger than 1568 px on the long edge are scaled down (smooth transform)
     before sending. Doodle coordinates are fractions, so they don't change.
     **Check before building:** 1568 px matches Anthropic's guidance; confirm what
     OpenRouter's main vision models accept and lower the cap if needed.
   - If `grabWindow` turns out to be off on scaled or negative-coordinate screens,
     fix it there (e.g. account for `screen.devicePixelRatio()`), and write down which
     Qt behaviour caused it in a comment.

## Test matrix (by hand, X11 session, `KAMI_DEBUG_DOODLES=1`)

Fill in the offset you measured (px). Target: ≤ 3 px.

| Setup | Region in middle | Region at screen edge | Notes |
|---|---|---|---|
| 1 monitor, 100% | | | |
| 1 monitor, 200% | | | |
| 2 monitors, both 100% | | | |
| 2 monitors, 100% + 200% | | | |
| 2 monitors, 100% + 150% (fractional) | | | |
| Secondary monitor **left of** primary (negative x) | | | |

**Different scaling per screen on X11:** GNOME and KDE on Xorg use one scale for every
monitor. To give Qt a different scale per screen, start Kami with, for example:
`QT_SCREEN_SCALE_FACTORS="DP-1=1;HDMI-1=2" kami` (get output names from `xrandr`).
**Decided 2026-10-08:** this Qt workaround is how v0.3 meets "two monitors with
different scaling" (see [Decisions](README.md#decisions-2026-10-08)). Proper
per-monitor scaling is out of scope here and comes later. Document the variable in the
README's multi-monitor notes.

No second monitor? Use a virtual one: `xrandr --setmonitor` or a dummy plug. Real
hardware is better for the final check.

## Files

| File | Change |
|---|---|
| `src/kami/geometry.py` | new, pure maths |
| `src/kami/ui/annotation.py` | use `layer_rect` / `to_point` |
| `src/kami/ui/overlay.py` | summon on the cursor's screen, downscale capture, calibration mode |
| `tests/test_geometry.py` | new |
| `README.md` | multi-monitor notes, `KAMI_DEBUG_DOODLES` under Troubleshooting |
| `ARCHITECTURE.md` | `geometry.py` box |

## Tests — `tests/test_geometry.py`

- [x] `test_layer_inside_screen_keeps_padding`: a region in the middle keeps the full padding
- [x] `test_layer_clipped_at_each_edge`: a region touching the left / right / top / bottom edge never extends past the screen, and `region_in_layer` shifts to match
- [x] `test_layer_on_negative_coordinates`: a screen at x = -1920 behaves like any other
- [x] `test_to_point_corners`: (0,0) and (1,1) map to the region's corners
- [x] `test_fit_inside_moves_not_resizes`: a box hanging off any edge is moved inside, with its size kept
- [x] `test_scaled_size`: 3000×1000 at 1568 → 1568×523; small sizes don't change

## Done when

- [ ] Every row of the matrix is filled in, and each offset is ≤ 3 px
- [ ] Phase exit criteria 1 and 2 ticked in the [README](README.md#phase-exit-criteria)
- [ ] The panel opens on the monitor you're using

## Commits

1. `add calibration mode for doodle alignment`
2. `add screen geometry helpers`
3. `keep doodles on the captured screen`
4. `downscale large captures before sending`
