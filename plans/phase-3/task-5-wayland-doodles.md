# Task 5 — Doodles on Wayland, or in the panel

**Size:** M · **Depends on:** Task 1, Task 3, Task 4 · **Branch:** `wayland-doodles` · **Owner:** both

## Goal

After a Wayland capture, the answer's doodles appear **on screen** where the desktop
allows it. Where it doesn't, they're drawn on a copy of the capture inside the panel, and
Kami says why in one line. Clicking that copy opens it larger. X11 doodles don't change.

## Why

- After Task 3, Wayland answers are text-only: `_show_lesson` draws only when
  `self.session.capture == "x11"`, because `AnnotationLayer.show_annotations` positions a
  small window with `setGeometry(layer_rect(...))`, and Wayland ignores client-set
  positions. The doodles would land wherever the compositor put the window.
- A capture from the desktop's picker has `region is None` (Task 4). Kami doesn't know
  where it was, so on-screen doodles can't work there on any desktop.
- All drawing code (circles, arrows, labels, `place_label`) lives in
  `AnnotationLayer.paintEvent` and `_note`, so it can't be reused for an image.

## Design

### Two ways to show doodles

1. **On-screen, full-screen layer** (Wayland, only on desktops in
   `session.ON_SCREEN_DESKTOPS`). Instead of a small window at the region, one
   transparent, input-transparent window **fills the captured screen**:
   `setScreen(s)` + `setGeometry(s.geometry())` + `showFullScreen()`. Its origin is the
   screen's top-left, so the doodles are drawn at `region − screen.topLeft()`
   (`geometry.local_region`), and no window positioning is needed. The 25 s fade,
   **Clear doodles** works as today. Two differences from the X11 layer, because on
   GNOME 46 this layer is black and on top (Q5), and the panel's **Clear doodles** button
   would be underneath it:
   - **📌 Keep is ignored**: the full-screen layer always fades after 25 s.
   - **`summon()` clears it**: the hotkey, the tray icon or `kami toggle` bring the
     panel back and remove the layer at once.

   Task 1, Q6 measured that `geometry()`, `screen()` and `isVisible()` are already right
   straight after `showFullScreen()`, before the compositor shows anything. Only
   `windowHandle().isExposed()` changes, at the first Expose (14–23 ms on GNOME 46). So
   Kami checks once, `LAYER_CHECK_MS` (100 ms) later, from a single-shot timer. If
   `windowHandle()` is `None` or `not windowHandle().isExposed()`, the layer hides
   itself and emits `layer_failed`. The panel then shows the doodles with reason
   `layer-failed`.

   This check can't see the two problems Task 1, Q5 found on GNOME 46: the layer was
   **opaque black** outside the doodles, and it **took focus** in 7 of 9 runs. That's
   why the layer is only used on desktops in `ON_SCREEN_DESKTOPS`, where those were
   measured. **Nothing is on that list in this phase**, so on Wayland this path runs only
   with `KAMI_DOODLES=screen`.
2. **In-panel.** A `QLabel` under the chat shows the capture scaled to fit 488×160 px
   (`geometry.fit_box`), with the same doodles painted on it. The panel is a fixed
   520×460 today (`overlay.py:145`), so while the preview shows, the panel grows by the
   preview's height plus the "why" line (`resize(520, 460 + extra)`), and it shrinks back
   to 520×460 when the preview is dropped. The chat keeps its full height. Clicking the
   preview opens a larger copy in its own window, up to 90 % of the screen's available
   size. Esc or a click closes it.

X11 keeps today's small window and `show_annotations` exactly as it is. Only its paint
code moves into the shared function, with `ink = 1.0`, so it draws the same pixels.

### Choosing

`session.doodle_plan(session, region_known, env)`, pure and tested, returns
`DoodlePlan(mode, reason)`. The first rule that matches wins:

| # | Condition | → mode | reason |
|---|---|---|---|
| 1 | `env["KAMI_DOODLES"] == "panel"` | panel | `forced` |
| 2 | `not region_known` (picker capture) | panel | `picker` |
| 3 | `env["KAMI_DOODLES"] == "screen"` | screen | `""` (a test switch, for trying a desktop that isn't on the list yet. On GNOME 46 it blacks out the screen and takes focus (Q5) until the doodles fade after 25 s, which 📌 Keep can't stop, or until you press the hotkey / click the tray icon, which brings the panel back and clears it) |
| 4 | `session.kind != "wayland"` | screen | `""` (X11 / unknown: today's layer) |
| 5 | `session.desktop in ON_SCREEN_DESKTOPS` | screen | `""` |
| 6 | otherwise | panel | `desktop` |

`ON_SCREEN_DESKTOPS` is `frozenset()` and **stays empty in this phase**. GNOME 46 failed
Task 1, Q5. A desktop joins only when `plans/phase-3/spike/layer_probe.py` on it prints
all three of these:
- `square visible in the shot: True`
- `transparent outside the square: True`
- `isActiveWindow False`

**and** you confirm by hand that clicks pass through (`layer_probe.py --hold 10`). For
KDE that is a "needs you" step. Adding it later is a one-line change plus a test. Every
Wayland desktop gets the panel now, so doodles never appear in the wrong place, and the
panel is what the second exit criterion asks for.

The frontend calls `doodle_plan(self.session, region is not None, os.environ)`.

### Shared drawing code

Move the body of `paintEvent` and `_note` into module-level
`paint_doodles(p, region, items, bounds, ink=1.0)` in `ui/annotation.py`. The layer and
the panel image both call it, so circles and labels look the same in both places.
`ink` scales every size: pen width 5, font 13 pt, arrow wing 22, arrow bend 25, label
width 220 and padding. With `ink = 1.0` the numbers are today's. In panel mode,
`ink = geometry.ink_scale(shown_w, source_w)`, clamped to 0.4–1.0, so a small preview
isn't all ink. `source_w` is the region's logical width, or the image width for a picker
capture.

### Telling the user why

The first in-panel result for each reason during a Kami run adds one line above the
image (`session.panel_note(session, reason)`):

| reason | text |
|---|---|
| `desktop` | *"GNOME on Wayland doesn't let apps draw over other windows, so the doodles are on this copy of your screen."* (`KDE Plasma`, `Sway`, `Hyprland`; anything else is "This desktop") |
| `picker` | *"The desktop's picker doesn't tell Kami where the area was, so the doodles are on this copy of it."* |
| `forced` | *"KAMI_DOODLES=panel is set, so the doodles are on this copy of your screen."* |
| `layer-failed` | *"Kami couldn't open its drawing layer on that screen, so the doodles are on this copy."* |

Later results with the same reason show the image without the line.

### Lifetime and privacy

- The preview pixmap is built from the held PNG in memory and never written to disk.
  **New chat**, a new capture and **Clear doodles** drop it and hide the label. Follow-up
  answers keep it, because they're about the same capture.
- **📌 Keep** applies only to X11's small on-screen layer. The full-screen Wayland layer
  ignores it (see "Two ways"), and the panel copy doesn't fade.
- `KAMI_DEBUG_DOODLES=1` (calibration) goes through the same choice, so the calibration
  pattern shows in whichever place the user would get. `learning.calibration_lesson` uses
  fractions of the image and needs no change.
- Log: `doodles mode=panel reason=desktop items=N` or `doodles mode=screen items=N`. No
  labels, no text.

## Contract

backend-dev builds this; frontend-dev calls it.

```python
# src/kami/session.py  (add)
ON_SCREEN_DESKTOPS: frozenset[str] = frozenset()   # empty: GNOME 46 failed Task 1, Q5; see the joining rule

@dataclass(frozen=True)
class DoodlePlan:
    mode: str    # "screen" | "panel"
    reason: str  # "" when mode == "screen"; else "desktop" | "picker" | "forced" | "layer-failed"

def doodle_plan(session: Session, region_known: bool, env: Mapping[str, str]) -> DoodlePlan: ...
def panel_note(session: Session, reason: str) -> str: ...   # unknown reason -> the "layer-failed" text
```

```python
# src/kami/geometry.py  (add)
def local_region(region: Rect, screen: Rect) -> Rect: ...           # region relative to the screen's top-left
def fit_box(w: int, h: int, max_w: int, max_h: int) -> tuple[int, int]: ...  # shrink to fit, never enlarge, min 1×1
def ink_scale(shown_w: float, source_w: float) -> float: ...        # clamp(shown/source, 0.4, 1.0); source_w <= 0 -> 1.0
```

## Backend part (backend-dev)

| File | Change |
|---|---|
| `src/kami/session.py` | `ON_SCREEN_DESKTOPS`, `DoodlePlan`, `doodle_plan`, `panel_note` |
| `src/kami/geometry.py` | `local_region`, `fit_box`, `ink_scale` |
| `tests/test_session.py` | `doodle_plan`, `panel_note` cases |
| `tests/test_geometry.py` | `local_region`, `fit_box`, `ink_scale` cases |

Steps:

1. Write the tests below first.
2. `doodle_plan`: implement the table's rules in order. `KAMI_DOODLES` is read from the
   `env` argument only, trimmed and lowercased. Values other than `panel` / `screen` are
   ignored.
3. `panel_note`: the texts in the table. Desktop names: `gnome` → GNOME, `kde` → KDE
   Plasma, `sway` → Sway, `hyprland` → Hyprland, other → "This desktop".
4. Keep `ON_SCREEN_DESKTOPS = frozenset()`. Put a comment above it with the joining rule,
   and say that GNOME 46 failed (Task 1, Q5: black outside the square, focus taken in 7
   of 9 runs).
5. `.venv-1/bin/python -m pytest -q` and `.venv-1/bin/ruff check .`.

## Frontend part (frontend-dev)

| File | Change |
|---|---|
| `src/kami/ui/annotation.py` | `paint_doodles()`; `AnnotationLayer.show_fullscreen()` + `layer_failed` signal; `render_doodled()`; `DoodlePreview` window |
| `src/kami/ui/overlay.py` | preview label + "why" line under the chat; panel grows while the preview shows; `_show_lesson` follows `doodle_plan`; Clear / New chat / new capture drop the preview |
| `README.md` | Explain screen row and Wayland notes: where doodles appear and why, `KAMI_DOODLES=panel` / `screen`. The warning for `screen`: on GNOME 46 the screen goes black for 25 s, 📌 Keep is ignored, and the hotkey or tray icon clears it at once |
| `ARCHITECTURE.md` | annotation box: "on screen, or in the panel on Wayland"; "How Explain screen works" step 5 |

Steps:

1. **`paint_doodles(p: QPainter, region: QRectF, items: list[Annotation], bounds: QRectF,
   ink: float = 1.0) -> None`**: move `paintEvent`'s and `_note`'s code here unchanged,
   except that the sizes are multiplied by `ink` and label bounds come from `bounds`
   (inset by `EDGE`). `AnnotationLayer.paintEvent` becomes
   `paint_doodles(QPainter(self), self._region, self._items, QRectF(self.rect()))`.
2. **`AnnotationLayer.show_fullscreen(region: QRect, items, screen: QScreen) -> None`**
   and a new signal `layer_failed = Signal()`:
   1. Set `self._region` from `local_region(_rect(region), _rect(screen.geometry()))`.
   2. Remember `self._target = screen`, then call `setScreen(screen)`,
      `setGeometry(screen.geometry())` and `showFullScreen()`.
   3. Start the fade timer **ignoring `self._keep`**, and set `self._fullscreen = True`.
      While `_fullscreen` is set, `set_keep(True)` doesn't stop the timer. `clear()`
      resets `_fullscreen` to `False`. Add a read-only property `is_fullscreen`.
   4. `QTimer.singleShot(LAYER_CHECK_MS, self._check_layer)`. `_check_layer` does nothing
      if the layer was cleared meanwhile. If `self.windowHandle()` is `None` or
      `not self.windowHandle().isExposed()`, it calls `clear()` and emits
      `layer_failed`.

   `show_annotations` is untouched. `LAYER_CHECK_MS = 100` is a module constant in
   `ui/annotation.py` (Q6: the first Expose came 14–23 ms after showing).
3. **`render_doodled(png: bytes, items, max_w: int, max_h: int, source_w: float) ->
   QPixmap`**:
   1. `QImage.fromData(png)`, scaled to `fit_box(...)` with smooth scaling.
   2. Paint on it with `QPainter` and `paint_doodles(p, QRectF(image.rect()), items,
      QRectF(image.rect()), ink_scale(shown_w, source_w))`.
   3. Return `QPixmap.fromImage`. A null image gives a null pixmap.
4. **`DoodlePreview(QWidget)`**: a plain top-level window with one `QLabel`. It's filled
   by `render_doodled` at 90 % of the panel screen's `availableGeometry()`, and closes on
   Esc or a mouse press. One instance, reused.
5. **`overlay.py` layout**:
   1. Under `self.output`, add `self.why = QLabel()` (object name `context`, word wrap,
      hidden) and `self.preview = QLabel()` (hidden, pointing-hand cursor).
   2. A mouse press on the preview opens `DoodlePreview` with the held PNG and items.
      Keep `self._preview_src = (png, items, source_w)` for that, in memory only, and a
      `self._notes_shown: set[str]` per run.
   3. Showing the preview calls `self.resize(520, 460 + pixmap.height() + why_height + 8)`,
      where `why_height` is the `why` label's `sizeHint().height()` when it's shown, and 0
      otherwise. Dropping it calls `self.resize(520, 460)`.
   4. Connect `self.doodles.layer_failed` to a slot that shows the held lesson's doodles in
      the panel with reason `layer-failed`. Keep `self._last_doodles = (png, items,
      source_w)` for that.
6. **`_show_lesson(png, region, where, question, lesson)`**: if `lesson.annotations`, call
   `plan = doodle_plan(self.session, region is not None, os.environ)`. Then:
   - `screen` and X11 / unknown: `self.doodles.show_annotations(region, …, where)`, as
     today.
   - `screen` and Wayland: find the `QScreen` whose `geometry() == where`. If there is
     one, call `show_fullscreen` (a late failure arrives through `layer_failed`). If there
     isn't, use the panel with reason `layer-failed` at once.
   - `panel`: `_show_panel_doodles(png, lesson.annotations, source_w, plan.reason)` sets the
     preview pixmap (`render_doodled(png, items, 488, 160, source_w)`), shows it, grows
     the panel, and shows the `why` line only if `reason not in self._notes_shown`.
   - Log the `doodles mode=…` line.
7. **`summon()`**: as its first line, `if self.doodles.is_fullscreen:
   self.doodles.clear()`. The X11 small layer isn't affected (`is_fullscreen` is
   `False` there), so X11 behaviour doesn't change.
8. **Dropping the preview**: `_set_chat` (New chat and new capture) and the
   **Clear doodles** button also hide `self.preview` and `self.why`, close
   `DoodlePreview`, and set `self._preview_src = None`. The Clear button gets a small
   slot that calls `self.doodles.clear()` and then this.
9. Remove Task 3's temporary `self.session.capture == "x11"` guard in `_show_lesson`. The
   plan replaces it.
10. `.venv-1/bin/python -m pytest -q` and `.venv-1/bin/ruff check .`.

## Tests

- [ ] `test_doodle_plan_x11_is_screen` in `tests/test_session.py`
- [ ] `test_doodle_plan_unknown_session_is_screen`
- [ ] `test_doodle_plan_wayland_listed_desktop_is_screen` (monkeypatch `ON_SCREEN_DESKTOPS`)
- [ ] `test_doodle_plan_wayland_unlisted_desktop_is_panel` (reason `desktop`)
- [ ] `test_doodle_plan_picker_capture_is_panel` (`region_known=False`, even on X11 and with `KAMI_DOODLES=screen`)
- [ ] `test_doodle_plan_env_panel_wins_everywhere` (reason `forced`)
- [ ] `test_doodle_plan_env_screen_forces_layer_on_wayland`
- [ ] `test_doodle_plan_ignores_other_env_values`
- [ ] `test_on_screen_desktops_only_known_names` (a subset of gnome / kde / sway / hyprland)
- [ ] `test_panel_note_names_the_desktop` (gnome, kde, other)
- [ ] `test_panel_note_reasons` (picker, forced, layer-failed, unknown reason → layer-failed text)
- [ ] `test_local_region_offsets_by_screen` in `tests/test_geometry.py` (incl. negative screen origin)
- [ ] `test_fit_box_shrinks_and_keeps_aspect`, `test_fit_box_never_enlarges`, `test_fit_box_minimum_one_pixel`
- [ ] `test_ink_scale_clamped`, `test_ink_scale_zero_source_is_one`

## Manual check

**Builder checks: offscreen only, no window on the real display, no portal call.**
Every script runs with `QT_QPA_PLATFORM=offscreen` and under `env -u KAMI_DOODLES`, so a
`KAMI_DOODLES` set in the builder's shell can't change `doodle_plan`'s answer.

- [ ] Panel rendering. In a throwaway script under `$TMPDIR`, run with
      `env -u KAMI_DOODLES QT_QPA_PLATFORM=offscreen .venv-1/bin/python -I <script>`:
      1. Create a `QApplication`.
      2. Build a white 800×600 PNG in memory.
      3. Call `render_doodled(png, learning.calibration_lesson().annotations, 488, 160, 800)`.
      4. Print the pixmap's size (expect 213×160) and how many pixels are close to `#FF6B9A`
         (expect more than 0).
      Don't save the image
- [ ] Same script, same `env -u KAMI_DOODLES QT_QPA_PLATFORM=offscreen` command: with
      `KamiOverlay(Config(), Session("wayland", "gnome"))`, call
      `overlay._show_lesson(png, QRect(0, 0, 800, 600), QRect(0, 0, 1920, 1080), "",
      learning.calibration_lesson())`. Then `overlay.preview.isVisibleTo(overlay)` is
      `True`, `overlay.height() > 460`, and `overlay.why.text()` names GNOME. After
      `overlay.new_chat()`, the preview is hidden and `overlay.height() == 460`
- [ ] Same command, the escape routes:
      1. `overlay.doodles.show_fullscreen(QRect(10, 10, 100, 100),
         learning.calibration_lesson().annotations, QGuiApplication.primaryScreen())`,
         then `overlay.doodles.set_keep(True)`. The fade timer is still active.
      2. Then `overlay.summon()`: `overlay.doodles.is_fullscreen` is `False` and the
         layer is hidden.
- [ ] `git diff` of `ui/annotation.py`: every size in `paint_doodles` is today's constant
      times `ink`, and `AnnotationLayer.paintEvent` passes no `ink` (so 1.0)

Yours (in `your-checklist.md`). Use `KAMI_DEBUG_DOODLES=1` (a free test pattern) with
the Phase 2 calibration page:

- [ ] GNOME Wayland: the doodles show in the panel, with the "why" line naming GNOME, and
      the corner circles sit on the image's corners
- [ ] Second capture in the same run: the image shows again, without the "why" line
- [ ] Click the image: a larger copy opens, and Esc closes it
- [ ] KDE Wayland VM: the same. Then run `layer_probe.py` there (Task 1's How to rerun)
      and the `--hold 10` click test. If it prints the three lines in the joining rule and
      clicks pass through, try `KAMI_DOODLES=screen` with Kami: are the doodles on the
      right spot? If yes, tell Claude to add `kde` to `ON_SCREEN_DESKTOPS`
- [ ] `KAMI_DOODLES=panel` on X11: the panel image shows all corner circles and labels
- [ ] Desktop picker capture: always in the panel, and the "why" line mentions the picker
- [ ] New chat and Clear doodles: the image goes away
- [ ] X11: calibration still ≤ 3 px, and fade / Keep / Clear unchanged

## Security

Run `/security-check`. Model output (labels) is drawn into an image and into a window,
and the screenshot is kept as a pixmap. Check that labels are drawn as plain text through
`paint_doodles` only (no rich text) and that the preview is dropped on New chat. Logs
hold counts and the reason only.

## Done when

- [ ] All tests above pass with the earlier ones, and ruff is clean
- [ ] On X11, `show_annotations` and its timing are unchanged, and `paint_doodles` with
      `ink=1.0` uses today's sizes
- [ ] On Wayland, on-screen mode is used only for desktops in `ON_SCREEN_DESKTOPS` or with
      `KAMI_DOODLES=screen`
- [ ] Both offscreen checks pass under `env -u KAMI_DOODLES`, with no window on the real
      display
- [ ] `ON_SCREEN_DESKTOPS` is empty, with a comment giving the joining rule and the GNOME 46
      result
- [ ] Your hand check: Phase exit criterion 2 is ticked in the
      [README](README.md#phase-exit-criteria)

## Commits

1. `add doodle placement choice and panel notes`
2. `share doodle painting between layer and panel`
3. `draw doodles in the panel when the screen can't be drawn on`
4. `draw doodles full-screen on wayland where supported`
