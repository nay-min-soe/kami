# Task 4 — The desktop's picker when capture is refused

**Size:** S · **Depends on:** Task 3 · **Branch:** `portal-picker` · **Owner:** frontend

## Goal

When the desktop refuses Kami's own screenshot (you clicked **Deny**, the portal failed or
timed out, the file couldn't be read, or the image didn't line up with your screens), the
panel offers **Use the desktop's picker**. You pick the area with the desktop's own
screenshot tool. Kami holds that image and waits for your question, as usual
(Decision 2's fallback).

## Why

After Task 3, a refused Wayland capture ends with a message and nothing else. Clicking
**Deny** in GNOME's dialog, or a desktop that won't allow non-interactive shots, leaves
the user stuck. The portal has a second mode for this, `interactive: true`: the desktop
shows its own picker and returns only what you picked. `ScreenshotPortal.request(
interactive=True)` already exists (Task 3 Contract), so this task adds the button and its
flow. No core change is needed.

## Design

- **When the button appears.** On Wayland only (`self.session.capture == "portal"`),
  after a **non-interactive** capture ends in any of these:
  1. a `cancelled`, `failed` or `timeout` reply (`_on_portal_reply`)
  2. a `ScreenshotFileError` (`_on_portal_file_failed`)
  3. an image `QImage` can't decode (`_on_portal_file`, null-image branch)
  4. `portal.CROP_FAILED`, either when cropping the screen's part for the selector
     (`_on_portal_file`) or when cropping the dragged box (`_crop_still`)

  Not after Esc in Kami's selector: that's the user changing their mind, not a refusal.
  Never on X11.
- **Where.** In the bottom row, between **New chat** and the stretch: `New chat · Use the
  desktop's picker · … · Stop · Copy`.
- **Clicking it:**
  1. Hide the button and the panel. Set `self._picking = True` and `self._still = None`.
  2. After 150 ms, call `self.screenshots.request(interactive=True)`. The desktop's own UI
     appears. The timeout is the usual 60 s.
- **Picker reply `ok`.** Same file handling as Task 3 (`portal.load_screenshot` in the
  worker). But there's **no selector and no crop**: the image is already what you picked
  (Task 1, Q11, still to be confirmed by hand). Decode, downscale with `scaled_size`,
  encode, then `_hold_capture(png, None, None)`.
- **Doodles.** `region is None`, so Task 3's guard in `_show_lesson` keeps the answer
  text-only. Task 5 puts these doodles in the panel.
- **Picker refused, cancelled, unreadable or timed out.** Show the same message as Task 3
  and **don't** show the button again (the user just used it). **Explain screen** still
  works for a fresh try.
- **`_picking` is reset in exactly one place**, `_capture_finished()`. It runs as the
  last line of every branch that ends a capture attempt (success or failure), **after**
  `_offer_picker()` has read the flag. So the flag is still `True` when the failure
  branch decides whether to offer the button.
- **The button goes away** on New chat, on a new capture (`_set_chat`), and when it's
  clicked.
- **Log:** `capture method=portal-picker status=… ms=…`, then `capture ready bytes=N`.
  Never the URI.

## Frontend part (frontend-dev)

| File | Change |
|---|---|
| `src/kami/ui/overlay.py` | `self.picker_button` in the bottom row; `self._picking`; `_offer_picker()`, `_use_picker()`, `_capture_finished()`; picker branch in `_on_portal_file` |
| `README.md` | Wayland notes: what the picker button is for, and that picked areas get no on-screen doodles |

Steps:

1. In `_build`, create `self.picker_button = QPushButton("Use the desktop's picker")`,
   hidden, `clicked` → `self._use_picker`. Insert it in the bottom row right after
   `self.new_chat_button`. Set `self._picking = False` in `__init__`.
2. `_offer_picker()`: show the button only if `self.session.capture == "portal"` and
   `not self._picking`.
3. `_capture_finished()`: `self._picking = False`.
4. Wire the failure branches Task 3 wrote, in this order: show the message, then
   `_offer_picker()`, then `_capture_finished()`:
   - the non-`ok` branch of `_on_portal_reply`
   - `_on_portal_file_failed`
   - the null-image branch of `_on_portal_file`
   - both `CROP_FAILED` branches (in `_on_portal_file` and `_crop_still`)
5. Success branches end with `_capture_finished()` too:
   - the end of `_crop_still`
   - the picker's `_hold_capture` call (step 7)
6. `_use_picker()`:
   1. Return if `self.screenshots.busy`.
   2. Hide the button, `self.hide()`, set `self._picking = True` and `self._still = None`.
   3. Set `self._capture_started = time.monotonic()` (the attribute Task 3 sets in
      `__init__`).
   4. `QTimer.singleShot(150, lambda: self.screenshots.request(interactive=True))`.
7. In `_on_portal_file`, right after the null-image check:
   1. If `self._picking`: downscale, encode, and call `_hold_capture(png, None, None)`.
   2. Add `portal.NOT_DELETED` if the file wasn't deleted.
   3. Call `_capture_finished()` and return. No selector, no crop.
8. In `_on_portal_reply`, log `method=portal-picker` when `self._picking`.
9. `_set_chat` also hides the button.
10. `.venv-1/bin/python -m pytest -q` and `.venv-1/bin/ruff check .`.

## Tests

No new core logic: the parsing and file handling are Task 3's, and their tests cover the
picker reply too. Check that the 202 + Task 3 tests still pass and ruff is clean.

## Manual check

**Builder checks: offscreen only, no portal call** (the picker would wait for a click).
Use a throwaway script under `$TMPDIR`, run with `QT_QPA_PLATFORM=offscreen`. Make a
**new overlay for each numbered check**, so state can't leak between them:

1. [ ] `KamiOverlay(Config(), Session("wayland", "gnome"))`, then
   `_on_portal_reply(ScreenshotReply("cancelled"))`:
   `picker_button.isVisibleTo(overlay)` is `True`, and `_picking` is `False`.
2. [ ] Same overlay as check 1, then `new_chat()`: the button is hidden.
3. [ ] New Wayland overlay. Set `_picking = True`, then
   `_on_portal_reply(ScreenshotReply("cancelled"))`. The button stays **hidden**
   (`isVisibleTo` is `False`), and afterwards `_picking` is `False`.
4. [ ] New Wayland overlay. Set `_picking = True`, then call `_on_portal_file(LoadedShot(<a
   white 600×400 PNG>, True))`. `_capture` holds a PNG that decodes to 600×400,
   `_capture[1] is None`, the selector is **not** visible, and `_picking` is `False`.
5. [ ] New Wayland overlay. Call `_on_portal_file(LoadedShot(b"not a png", True))`. The
   button shows, and `_still` is `None`.
6. [ ] `KamiOverlay(Config(), Session("x11", "gnome"))`, then
   `_on_portal_reply(ScreenshotReply("cancelled"))`. The button never shows.

Yours (in `your-checklist.md`), on GNOME 46 Wayland with an API key:

- [ ] Remove the stored grant (Task 1's How to rerun, Q2 Deny code), then Explain screen →
      click **Deny**. The cancel message and **Use the desktop's picker** appear in the
      bottom row
- [ ] Click it: GNOME's screenshot UI appears. Pick an area. The panel says *Screen
      captured*, and the answer to "what is this?" is about the picked area. Note
      whether the image was really only your pick (Task 1, Q11)
- [ ] Click the picker button, then press Esc in GNOME's UI. The message appears, and the
      button doesn't come back
- [ ] New chat: the button goes away
- [ ] KDE Wayland VM: the same
- [ ] X11: the button never appears

## Security

Run `/security-check`. A second path reads and deletes the portal's file (through Task
3's `load_screenshot`, unchanged) and holds a screenshot in memory. Check that the picker
path logs no URI, doesn't skip `load_screenshot`, and leaves `_still` empty.

## Done when

- [ ] Offscreen checks 1–6 pass, with no window on the real display and no portal call
- [ ] A picker capture goes through `portal.load_screenshot` and `_hold_capture(png, None,
      None)`, and never opens Kami's selector
- [ ] `_picking` is reset only in `_capture_finished()`, and every capture branch ends
      there
- [ ] The button can't appear on X11
- [ ] Your hand check: after **Deny**, the picker gives a working Explain screen on GNOME
      and KDE

## Commits

1. `offer the desktop picker when capture is refused`
