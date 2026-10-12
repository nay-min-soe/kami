# Task 3 — Screen capture through the portal

**Size:** M · **Depends on:** Task 1, Task 2 · **Branch:** `portal-capture` · **Owner:** both

## Goal

On Wayland, **Explain screen** first takes a screenshot through
`org.freedesktop.portal.Screenshot`. Kami then shows that still image full-screen, and you
drag your box on it. Kami crops the same image and waits for your question, exactly as on
X11 (capture → hold → question → answer). The first time, the desktop may ask for
permission. If you refuse, Kami says so in plain words, and Task 4 adds the desktop's
picker as a way out. X11 keeps using `grabWindow` over the live screen, with no code
change.

## Why

- `_capture_region` (`ui/overlay.py`) grabs synchronously with `screen.grabWindow(0, …)`.
  On Wayland that pixmap is empty, and under XWayland it is pure black (Task 1, Q9). The
  panel then shows `session.capture_failed_message`.
- **Kami's selector can't sit over the live screen on GNOME** (Task 1, Q5). A translucent
  full-screen window there is backed by opaque black: with the selector's dim fill, every
  spot reads `(11, 10, 16)`, so you would drag over a black screen. Painting a still
  screenshot as the selector's own, opaque background avoids that. This is Plan change 3,
  and it is how Decision 2 now works on Wayland.
- The portal is **asynchronous**. `Screenshot("", options)` returns a `Request` object
  path, and the result arrives later as that object's `Response(u response, a{sv}
  results)` signal: `response` is 0 for success, 1 if the user cancelled and 2 for any
  other error. On GNOME 46, `results` holds exactly one key, `uri` (a `str`, `file://` to a
  PNG straight in `~/Pictures/`) (Task 1, Q1 and Q3).
- PR #20's flow holds the capture before the panel comes back. On Wayland the panel (and
  the selector) must be hidden **while the portal shoots**, and that happens before you
  drag. So neither can end up in the image.

## Design

### Flow on Wayland (`session.capture == "portal"`)

1. **Explain screen**:
   1. The panel remembers its own screen, `self.screen()`. That is right on Wayland
      (Task 1, Q6), unlike `QCursor.pos()`, which stays `(0, 0)` there (Q7).
   2. It hides and clears old doodles.
   3. After `portal.HIDE_DELAY_MS` (150 ms, confirmed by Q10), it calls the portal with
      `{"handle_token": portal.new_token(), "interactive": False}`.

   Nothing of Kami's is on screen while the portal shoots. If the desktop shows a
   permission dialog, that is what you see. The timeout is 60 s
   (`portal.SCREENSHOT_TIMEOUT_MS`). On timeout, Kami calls `Request.Close`, which also
   closes the dialog.
2. **Reply `ok`**:
   1. A worker thread reads the PNG and deletes the file (`portal.load_screenshot`).
   2. Back on the main thread, Kami decodes it once into `self._still` (a `QImage`, in
      memory only).
   3. It crops the remembered screen's part out of it with
      `geometry.crop_rect(screen_rect, screens, w, h)`.
   4. It starts the selector on that screen with the crop as its background:
      `RegionSelector.start(screen, background)`.

   That takes about 0.5–0.8 s after the click (the portal's own time, Q10).
3. **The selector over the still image** paints the background scaled to its own rect,
   dimmed outside your box and at full brightness inside it. Kami's background is opaque,
   so GNOME's black backing never shows. The drag, Esc and the minimum-size rule are as
   today. It emits the box in global logical coordinates: the local box offset by the
   screen's `geometry().topLeft()`.
4. **Box chosen**: crop `self._still` with `crop_rect(region, screens, w, h)`, downscale
   with the existing `scaled_size(…, learning.MAX_IMAGE_EDGE)`, encode as PNG, and drop
   `self._still`. Then it's the X11 path: `_hold_capture(png, region, where)` summons the
   panel, starts a fresh chat, and holds `self._capture = (png, region, where)` until you
   type a question (`_ask_about_capture` is unchanged). `KAMI_DEBUG_DOODLES=1` still skips
   the question and goes to `_show_lesson` with the calibration lesson.
5. **Esc or a tiny drag**: drop `self._still` and summon the panel, as `cancelled` does
   today.
6. **Reply `cancelled`, `failed` or `timeout`**: the panel comes back with
   `portal.reply_message(reply)`. Task 4 adds the picker button under it.
7. **`crop_rect` returns `None`** (the image doesn't match the screen layout, Q4) at step
   2 or 4: drop `self._still`, show `portal.CROP_FAILED`. Task 4 adds the picker here too.

### X11

`explain_screen`, `_on_region`, `RegionSelector.start()` with no arguments, and the
`grabWindow` branch of `_capture_region` are today's code. The only X11-visible change is
that `_capture_region`'s tail moves into `_hold_capture` (same calls, same order).

### Doodles in this task

Task 5 decides where Wayland doodles go. Until then, `_show_lesson` draws on screen only
when `self.session.capture == "x11"` and `region is not None`. On Wayland the answer is
text only.

### QtDBus rules (Task 1, Q1 and Q13)

- **The only slot that can read a `Response`** is a typed one: `@Slot("uint",
  "QVariantMap")`, connected with the `str` from `SLOT("<name>(uint,QVariantMap)")`.
  `bytes` is refused, `@Slot(int, …)` is refused for D-Bus `u`, and a `QDBusMessage` slot
  gets an unreadable `QDBusArgument` for the map.
- **Never pass QtDBus a value it can't marshal** (a tuple, a list of tuples, a nested
  struct). The failed call can leave the next blocking call stuck past its timeout.
  Screenshot needs only `str`, `bool` and a `dict[str, str | bool]`, which work.
- **`to_python` drops a `QDBusArgument`** (→ `None`): PySide6 6.11.2 can't read one.
  Through the typed slot, the Screenshot results are already `{'uri': str}`. Object paths
  arrive as `QDBusObjectPath`, and `to_python` turns them into `str`.
- **Sender filter**: subscribe with the service name `org.freedesktop.portal.Desktop` on
  the predicted request path, **before** the call. QtDBus then ignores the same signal
  from any other sender (confirmed in Q13). If the returned handle differs from the
  prediction (it never did in 18 runs), connect again on the returned path.

### Edge cases

- **One request at a time.** While `ScreenshotPortal.busy` or the selector is open,
  **Explain screen** does nothing.
- **The hotkey summons the panel during the portal call.** That's allowed, and the panel
  may then be in the still image. Known limit, documented.
- **Which app the permission belongs to.** xdg-desktop-portal 1.18.4 files the grant
  under the app that *launched* Kami, taken from its systemd scope (Q2: it was stored for
  `com.microsoft.VSCode`). So the first dialog names that app, and starting Kami another
  way (terminal, autostart) can ask again. Task 7 documents how to start Kami as
  `org.kami.Kami` for one stable grant. This task only says so in the README.

### Privacy

- `self._still` (the full screen) lives only from the portal reply until the crop or the
  cancel. Then it's dropped. It is never written, logged or sent: only the crop is sent,
  and only after you ask.
- `portal.load_screenshot` is the only Kami code that opens the portal's file. It accepts
  only:
  - a `file://` URI with an empty or `localhost` host and an absolute path
  - a regular file, checked with `lstat` first, then opened with
    `O_RDONLY | O_NOFOLLOW | O_NONBLOCK` and checked again with `fstat`
  - at most 64 MB: it reads at most `max_bytes + 1` bytes
- It deletes that exact path in a `finally` once the URI and `lstat` checks have passed,
  whether or not the read worked. It never deletes anything that failed those checks.
- Its error messages never contain the path, and its exceptions carry no chained
  `OSError`. It notes the failure inside `except` and raises `ScreenshotFileError` after
  the `except` block, so `__context__` and `__cause__` are both `None`.
- `ScreenshotReply.uri` and `LoadedShot.png` are left out of the dataclass `repr`.
- If the delete fails: log `screenshot temp file not deleted` (no path), and the panel adds
  the line `portal.NOT_DELETED`.
- Log: `capture method=portal status=<ok|cancelled|failed|timeout> ms=N`, then
  `capture ready bytes=N` after the crop. Never the URI.

## Contract

backend-dev builds the core part; frontend-dev builds `ui/portal.py`,
`ui/region_select.py` and the panel changes, and calls the core.

```python
# src/kami/portal.py  (new, core: no Qt)
from collections.abc import Mapping
from dataclasses import dataclass, field

HIDE_DELAY_MS = 150            # wait after hiding the panel (Task 1, Q10: enough on GNOME 46)
SCREENSHOT_TIMEOUT_MS = 60_000
MAX_SCREENSHOT_BYTES = 64 * 1024 * 1024
CROP_FAILED = "Kami couldn't line the screenshot up with your screens."
READ_FAILED = "Kami couldn't read the screenshot"   # the panel adds ": <reason>" or "."
NOT_DELETED = "Kami couldn't delete the desktop's temporary screenshot file."

@dataclass(frozen=True)
class ScreenshotReply:
    status: str                              # "ok" | "cancelled" | "failed" | "timeout"
    uri: str = field(default="", repr=False) # only when status == "ok"; never logged
    reason: str = ""                         # short, safe to log: "response=2", "no uri", "not a file uri", "timeout", "dbus error"

@dataclass(frozen=True)
class LoadedShot:
    png: bytes = field(repr=False)  # the file's bytes as the portal wrote them (PNG)
    deleted: bool                   # False if the file could not be removed

class ScreenshotFileError(Exception):
    """Plain-words reason; never contains the path; raised with no chained exception."""

def new_token() -> str: ...                                   # "kami_" + 16 hex chars
def request_path(unique_name: str, token: str) -> str: ...
    # ":1.42", "kami_ab" -> "/org/freedesktop/portal/desktop/request/1_42/kami_ab"
def parse_screenshot_reply(code: object, results: Mapping[str, object]) -> ScreenshotReply: ...
def timed_out() -> ScreenshotReply: ...                       # ScreenshotReply("timeout", reason="timeout")
def reply_message(reply: ScreenshotReply) -> str: ...         # panel text for cancelled / failed / timeout
def load_screenshot(uri: str, max_bytes: int = MAX_SCREENSHOT_BYTES) -> LoadedShot: ...
    # raises ScreenshotFileError; runs on the worker thread
```

```python
# src/kami/geometry.py  (add)
def crop_rect(region: Rect, screens: list[Rect], image_w: int, image_h: int) -> Rect | None: ...
    # region and screens: Qt logical global coordinates. Assumes the image covers the
    # bounding box of all screens at one uniform scale k = image_w / bbox.w (Task 1, Q4:
    # k = 1.000 on one 100 % screen; 2 screens / other scales still to be measured).
    # Returns whole pixels inside the image, or None if the layout doesn't match
    # (|image_h - bbox.h * k| > max(2, 1 % of image_h)), there are no screens, or the
    # clamped crop is empty. Used twice: the screen's part (selector background) and
    # the dragged box.
```

Rules for `parse_screenshot_reply`:

| `code` | `results` | → |
|---|---|---|
| 0 | `uri` is a `str` starting with `file://` | `ok`, `uri` set |
| 0 | `uri` missing or not a `str` | `failed`, `no uri` |
| 0 | `uri` with any other scheme | `failed`, `not a file uri` (the URI isn't kept) |
| 1 | anything | `cancelled` |
| 2 or any other int | anything | `failed`, `response=<code>` |
| not an `int` (or a `bool`) | anything | `failed`, `bad response` |

Frontend side (`src/kami/ui/portal.py`, new, UI layer):

```python
def to_python(value: object) -> object | None: ...
    # D-Bus value -> plain Python, recursively:
    #   QDBusVariant          -> to_python(value.variant())
    #   QDBusObjectPath       -> value.path()  (a str)
    #   dict                  -> {str(k): to_python(v)}, entries that convert to None dropped
    #   list / tuple          -> same container type, items that convert to None dropped
    #   str, bool, int, float -> unchanged
    #   QDBusArgument, bytes, QByteArray, anything else -> None (dropped; PySide6 can't read them, Q13)

class PortalRequest(QObject):
    replied = Signal(int, dict)        # response code, results already passed through to_python
    timed_out = Signal()
    failed = Signal(str)               # the D-Bus call itself failed; the error name
    def call(self, interface: str, method: str, args: list, token: str, timeout_ms: int) -> None: ...
        # args must hold only str / bool / int and dict[str, str | bool | int] (QtDBus rules)

class ScreenshotPortal(QObject):
    finished = Signal(object)          # always a portal.ScreenshotReply, exactly once per request()
    @property
    def busy(self) -> bool: ...
    def request(self, interactive: bool,
                timeout_ms: int = portal.SCREENSHOT_TIMEOUT_MS) -> None: ...
```

```python
# src/kami/ui/region_select.py  (change)
class RegionSelector(QWidget):
    selected = Signal(QRect)   # global logical coordinates (unchanged)
    cancelled = Signal()       # unchanged
    def start(self, screen: QScreen | None = None, background: QImage | None = None) -> None: ...
        # no arguments: today's live-screen selector (X11)
        # screen + background: full-screen on `screen`, painting `background` (Wayland)
```

Who handles errors:
- `ScreenshotPortal` never raises. `PortalRequest.failed` becomes
  `finished(ScreenshotReply("failed", reason="dbus error"))`, and a timeout becomes
  `finished(portal.timed_out())`.
- `load_screenshot` raises `ScreenshotFileError`. `run_in_background` turns it into
  `on_error(message)`, and the panel shows `f"{portal.READ_FAILED}: {message}"`.

## Backend part (backend-dev)

| File | Change |
|---|---|
| `src/kami/portal.py` | new: the core Contract above |
| `src/kami/geometry.py` | `crop_rect` |
| `tests/test_portal.py` | new |
| `tests/test_geometry.py` | `crop_rect` cases |
| `ARCHITECTURE.md` | `portal.py` box in Core and in "The one rule for layers" |

Steps:

1. `geometry.crop_rect`:
   1. Return `None` for an empty `screens` list.
   2. Compute the screens' bounding box and `k = image_w / bbox.w`, and check the height
      tolerance.
   3. Map: `x0 = floor((region.x - bbox.x) * k)`, `y0` the same,
      `x1 = ceil((region.right - bbox.x) * k)`, `y1` the same.
   4. Clamp to `[0, image_w] × [0, image_h]`. Return `None` if the result is empty.
2. `portal.new_token()` uses `secrets.token_hex(8)`. `request_path` strips the leading
   `:` and replaces `.` with `_` in the unique name.
3. `parse_screenshot_reply` follows the table. `reply_message` texts:
   - cancelled: *"Screenshot cancelled. Kami needs permission to see your screen for
     Explain screen. Click Explain screen to try again."*
   - failed: *"The desktop couldn't take the screenshot. Run `kami doctor` to see why."*
   - timeout: *"The desktop's screenshot service didn't answer within 60 seconds. Click
     Explain screen to try again."*

   Task 4 doesn't change these texts. It only adds a button under them.
4. `load_screenshot(uri, max_bytes)`, in this order:
   1. Parse with `urllib.parse.urlsplit`, then `unquote` the path. If the scheme isn't
      `file`, the host isn't empty or `localhost`, or the path isn't absolute, refuse
      with *"the screenshot address isn't a local file"*. Nothing is deleted.
   2. `os.lstat(path)`: if it isn't a regular file (`stat.S_ISREG`), refuse with *"the
      screenshot isn't a regular file"*. Nothing is deleted. If `lstat` itself fails,
      refuse with *"couldn't read the screenshot file"*.
   3. From here on, `try … finally: unlink` the path:
      1. `fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)`.
      2. `os.fstat(fd)`: re-check `S_ISREG`, and that `st_size <= max_bytes`.
      3. Read in chunks until EOF or `max_bytes + 1` bytes. More than `max_bytes` means
         "too big".
      4. Close `fd`.
   4. **Error style (no chained exceptions):** inside `except OSError:` only set
      `problem = "couldn't read the screenshot file"`. After the `try` statement, if
      `problem` is set, `raise ScreenshotFileError(problem)`. Every refusal is raised the
      same way, outside any `except` block.
   5. The `finally` sets `deleted` from whether `os.unlink` succeeded. `FileNotFoundError`
      counts as deleted.
5. Update `portal.py`'s module docstring with the privacy rules above.
6. `.venv-1/bin/python -m pytest -q` and `.venv-1/bin/ruff check .`.

## Frontend part (frontend-dev)

| File | Change |
|---|---|
| `src/kami/ui/portal.py` | new: `to_python`, `PortalRequest`, `ScreenshotPortal` (Kami's QtDBus client) |
| `src/kami/ui/region_select.py` | `start(screen=None, background=None)`; with a background: full-screen on that screen, paints the still image |
| `src/kami/ui/overlay.py` | Wayland branch in `explain_screen`; portal reply → still image → selector → crop; shared `_hold_capture`; `_capture` allows `None` region / screen; on-screen doodles only on X11 |
| `README.md` | Explain screen row and Wayland notes: you drag on a still copy of your screen; the permission dialog names the app that started Kami; doodles text-only on Wayland until Task 5 |
| `ARCHITECTURE.md` | "How Explain screen works" steps 1–2 (see step 9) |

Steps:

1. **`to_python`**: the table in the Contract.
2. **`PortalRequest.call(...)`**:
   1. `bus = QDBusConnection.sessionBus()`. Compute
      `path = portal.request_path(bus.baseService(), token)`.
   2. `bus.connect("org.freedesktop.portal.Desktop", path, "org.freedesktop.portal.Request",
      "Response", self, SLOT("_on_response(uint,QVariantMap)"))`, where `_on_response` is
      decorated `@Slot("uint", "QVariantMap")`. Copy the working connect line from
      `plans/phase-3/spike/portal_shot.py`.
   3. Make the call asynchronously (`asyncCall` + `QDBusPendingCallWatcher`) on
      `org.freedesktop.portal.Desktop` / `/org/freedesktop/portal/desktop`:
      - a call error stops the timer, disconnects, and emits `failed(<error name>)`
      - if the returned `QDBusObjectPath` differs from `path`, connect again on that one
   4. Start a single-shot `QTimer(timeout_ms)`. On a `Response`, stop the timer,
      disconnect, and emit `replied(int(code), to_python(results) or {})`.
   5. On timeout, call `org.freedesktop.portal.Request.Close` on the path (no reply
      needed), disconnect, and emit `timed_out`.
3. **`ScreenshotPortal.request(interactive)`**: options
   `{"handle_token": portal.new_token(), "interactive": <bool>}`. Turn:
   - `replied` into `finished(portal.parse_screenshot_reply(code, results))`
   - `timed_out` into `finished(portal.timed_out())`
   - `failed` into `finished(ScreenshotReply("failed", reason="dbus error"))`

   `busy` is `True` from `request` until `finished`.
4. **`region_select.py`**:
   - With no arguments: today's code, untouched.
   - With `screen` and `background`:
     1. Keep `self._background = background` and
        `self._screen_origin = screen.geometry().topLeft()`.
     2. `setScreen(screen)`, `setGeometry(screen.geometry())`, `showFullScreen()`.
   - In `paintEvent`, if `self._background` is set:
     1. `drawImage(self.rect(), self._background)`.
     2. Fill `QColor(30, 27, 46, 90)` over everything **except** the box (no
        `CompositionMode_Clear`, because the background is the content).
     3. Draw the dashed box as today.
     4. Otherwise, today's paint code.
   - The emit offset is `self._screen_origin` when set, otherwise
     `self.geometry().topLeft()` as today.
   - On hide (selected or cancelled), drop `self._background` and reset
     `self._screen_origin`.
5. **`overlay.py`**:
   1. In `__init__`, add:
      - `self.screenshots = ScreenshotPortal(self)`, with
        `finished.connect(self._on_portal_reply)`
      - `self._still: QImage | None = None`
      - `self._capture_started = 0.0`: `time.monotonic()` when a portal request starts;
        the `ms=` log uses it. It's set in `__init__` so a reply handler never meets a
        missing attribute. Task 4's `_use_picker` sets it too.
   2. **`explain_screen()`**:
      - On Wayland: return early if `self.screenshots.busy` or the selector is visible.
        Remember `self._shot_screen = self.screen()`, set
        `self._capture_started = time.monotonic()`, then `hide()`
        and `self.doodles.clear()`. After `portal.HIDE_DELAY_MS`, call
        `self.screenshots.request(interactive=False)`.
      - On X11: today's code.
   3. **`_on_region(region)`**:
      - On Wayland: `self._crop_still(region)` right away (nothing to wait for).
      - On X11: today's 150 ms timer → `_capture_region`.
   4. **`_hold_capture(png, region, where)`**: `self.summon()`, then today's lines from
      `self.new_chat()` to the end of `_capture_region`, unchanged. The X11 branch of
      `_capture_region` keeps its grab and encode code. When the image is empty, it calls
      `summon()` and shows the message, as today. Otherwise it calls
      `_hold_capture(bytes(data), region, screen.geometry())`.
   5. **`selector.cancelled`**: on Wayland, also set `self._still = None` before
      `summon()`.
6. **`_on_portal_reply(reply)`**:
   - Log `capture method=portal status=… ms=…` (never `reply.uri`, never `%r` of the
     reply).
   - If `ok`: `run_in_background(portal.load_screenshot, reply.uri,
     on_done=self._on_portal_file, on_error=self._on_portal_file_failed)`.
   - Otherwise: `summon()` and `_say(f"**Oops:** {portal.reply_message(reply)}")`.
   - `_on_portal_file_failed(message)`: `summon()`, then
     `_say(f"**Oops:** {portal.READ_FAILED}: {message}")`.
7. **`_on_portal_file(shot)`**:
   1. `image = QImage.fromData(shot.png)`. If it's null: `summon()`, show
      `f"{portal.READ_FAILED}."` and stop.
   2. Keep `self._still = image` and `self._not_deleted = not shot.deleted`. If the file
      wasn't deleted, log the warning.
   3. `screens = [_rect(s.geometry()) for s in QGuiApplication.screens()]`. Import `_rect`
      from `kami.ui.annotation`.
   4. `part = crop_rect(_rect(self._shot_screen.geometry()), screens, image.width(),
      image.height())`. On `None`: drop `self._still`, `summon()`, show
      `portal.CROP_FAILED`, and stop.
   5. `self.selector.start(self._shot_screen, image.copy(QRect(...part...)))`.
8. **`_crop_still(region)`**:
   1. `crop_rect(_rect(region), screens, w, h)` on `self._still`. On `None`: same as
      7.4.
   2. Copy, downscale with `scaled_size`, and encode as PNG through `QBuffer`. Set
      `self._still = None`.
   3. Call `_hold_capture(png, region, self._shot_screen.geometry())`. If
      `self._not_deleted`, add `portal.NOT_DELETED` under the "Screen captured" line.
9. **`_show_lesson`**: draw on screen only if `lesson.annotations and region is not None
   and self.session.capture == "x11"`. The `_capture` type hint becomes
   `tuple[bytes, QRect | None, QRect | None] | None` (Task 4 holds `None` there).
10. Change `ARCHITECTURE.md`'s "How Explain screen works" steps 1–2:
    - X11: unchanged.
    - Wayland: the portal takes a screenshot first, you drag on that still image, and
      Kami crops it.
11. `.venv-1/bin/python -m pytest -q` and `.venv-1/bin/ruff check .`.

## Tests

- [ ] `test_crop_single_screen_100` in `tests/test_geometry.py` (1920×1080 screen, image 1920×1080)
- [ ] `test_crop_single_screen_200` (logical 1920×1080, image 3840×2160)
- [ ] `test_crop_fractional_125` (logical 1536×864, image 1920×1080, rounds outward)
- [ ] `test_crop_second_screen` (two screens side by side, region on the right one)
- [ ] `test_crop_whole_screen_of_two` (the screen rect itself, for the selector's background)
- [ ] `test_crop_negative_origin` (screen at x = −1920)
- [ ] `test_crop_clamped_to_image` (a region past the edge never gives pixels outside the image)
- [ ] `test_crop_layout_mismatch_is_none` (image height doesn't fit the screens)
- [ ] `test_crop_no_screens_is_none`
- [ ] `test_request_path_from_unique_name` in `tests/test_portal.py`
- [ ] `test_new_token_is_unique_and_safe` (only `[A-Za-z0-9_]`, starts with `kami_`)
- [ ] `test_reply_ok_file_uri`, `test_reply_cancelled`, `test_reply_error_code`
- [ ] `test_reply_missing_uri`, `test_reply_rejects_non_file_uri`, `test_reply_bad_code_type`
- [ ] `test_reply_repr_hides_uri` (`"file://" not in repr(reply)`)
- [ ] `test_reply_message_never_contains_uri`
- [ ] `test_load_reads_and_deletes` (`tmp_path` PNG bytes → returned, file gone, `deleted=True`)
- [ ] `test_load_rejects_other_schemes` (`http://`, `/abs/path`, `file://otherhost/x`; the files are untouched)
- [ ] `test_load_rejects_relative_path`
- [ ] `test_load_refuses_symlink_and_keeps_target` (symlink → error, the target file is untouched)
- [ ] `test_load_refuses_fifo_without_blocking` (`os.mkfifo` in `tmp_path` → error at once, FIFO left in place)
- [ ] `test_load_too_big_is_deleted_and_refused` (`max_bytes=10`, 11-byte file)
- [ ] `test_load_missing_file_error_has_no_path`: `__cause__ is None`, `__context__ is None`, and the path is not in `str(exc)` or `"".join(traceback.format_exception(exc))`
- [ ] `test_load_percent_encoded_path` (`file:///…/a%20b.png` in `tmp_path`)

## Manual check

**Builder checks: no window on the real display, at most 3 live portal calls.**

1. [ ] **Live smoke (1 portal call).** The screenshot grant for this machine's builder
   scope (`com.microsoft.VSCode`) is already stored (Q2), so the call is silent. If it
   prints `timeout`, stop: write "needs you: Allow" in the build report and don't call
   again.

   ```bash
   QT_QPA_PLATFORM=offscreen .venv-1/bin/python -I -c '
   import sys
   from PySide6.QtCore import QCoreApplication, QTimer
   from kami import portal
   from kami.ui.portal import ScreenshotPortal
   app = QCoreApplication(sys.argv)
   shots = ScreenshotPortal()
   def done(reply):
       print("status", reply.status, reply.reason)
       if reply.status == "ok":
           shot = portal.load_screenshot(reply.uri)
           print("bytes", len(shot.png), "deleted", shot.deleted)
       app.quit()
   shots.finished.connect(done)
   QTimer.singleShot(0, lambda: shots.request(False, timeout_ms=20_000))
   app.exec()'
   ```

   It prints `status ok`, a byte count and `deleted True`. Then
   `find ~/Pictures -maxdepth 1 -newermt '-5 minutes' -name '*.png'` prints nothing.
2. [ ] **Still-image flow, offscreen (no portal call).** In a throwaway script under
   `$TMPDIR`, run with `QT_QPA_PLATFORM=offscreen`:
   1. Create a `QApplication` and `KamiOverlay(Config(), Session("wayland", "gnome"))`.
   2. Build a white PNG **the size of the offscreen screen**,
      `QGuiApplication.primaryScreen().geometry().size()`. That's 800×800 under
      `offscreen`; a 1920×1080 image wouldn't match the layout, and `crop_rect` would
      return `None`. Wrap it as `LoadedShot(<its bytes>, True)`.
   3. Set `overlay._shot_screen = QGuiApplication.primaryScreen()` and call
      `overlay._on_portal_file(shot)`. `overlay.selector.isVisible()` is `True`, and its
      `_background` is 800×800.
   4. Emit `overlay.selector.selected.emit(QRect(100, 100, 400, 300))`.
      `overlay._capture` holds a PNG that decodes to 400×300, and `overlay._still` is
      `None`.
   5. Repeat steps 3–4 with `selector.cancelled.emit()` instead: `_still` is `None`, and
      `_capture` is `None`.
3. [ ] `to_python` check, offscreen, no bus: `to_python(QDBusVariant(2)) == 2`,
   `to_python(QDBusObjectPath("/a/b")) == "/a/b"`, `to_python(QDBusArgument()) is None`,
   and `to_python({"uri": "file:///x", "n": QDBusArgument()}) == {"uri": "file:///x"}`.
4. [ ] `grep -c "file://" ~/.local/state/kami/kami.log` prints `0`.

Yours (in `your-checklist.md`), on GNOME 46 Wayland with an API key:

- [ ] Explain screen: after about half a second, your screen appears dimmed and still (no
      black screen). Drag a box: the box shows at full brightness. The panel says *Screen
      captured*. Type "what is this?": the answer is about what you selected (text only)
- [ ] Esc in the selector: the panel comes back, with nothing captured
- [ ] Start Kami from a plain **Terminal** (not VS Code): note whether the dialog appears
      again, and which app it names
- [ ] Click **Deny** in that dialog: the cancel message appears
- [ ] `KAMI_DEBUG_DOODLES=1`: after the drag, the calibration text appears at once
- [ ] `~/Pictures`: no Kami screenshot left behind
- [ ] KDE Wayland VM: the same checks
- [ ] X11: `KAMI_DEBUG_DOODLES=1` calibration is still ≤ 3 px (`_capture_region` was split)

## Security

Run `/security-check`. This task:
- reads and deletes a file named by another process: path and scheme checks, symlinks,
  FIFOs, size cap, no chained exceptions
- holds a full-screen still image in memory: when it's dropped, and that it's never sent
  or logged
- listens on the session bus: sender filtering, request-path matching

Logs must hold status and counts only, never the URI. `repr` of a reply must not show it.

## Done when

- [ ] All tests above pass with the 202 earlier ones, and ruff is clean
- [ ] On Wayland, `_capture_region` and `grabWindow` are never called, and the selector
      always paints a still image. On X11, `explain_screen`, the selector and the grab
      run the same code as before (`git diff` shows a move only on that path)
- [ ] Builder checks 1–4 pass, with at most 3 portal calls and no window on the real
      display. Or the build report records `timeout` and the "Allow" step
- [ ] No code path logs or shows the portal's URI or path, and `self._still` is `None`
      after every crop, cancel and failure
- [ ] On Wayland, nothing is drawn on screen (text-only answers until Task 5)
- [ ] Your hand check: Explain screen captures on GNOME Wayland and KDE Wayland, and no
      screenshot file outlives the capture

## Commits

1. `add crop maths for portal screenshots`
2. `parse screenshot portal replies and load the file safely`
3. `add screenshot portal client`
4. `select the region on a still portal screenshot on wayland`
