"""Phase 3 spike, Q5 + Q6 + Q10: a full-screen, click-through layer on Wayland.

Shows the window Task 5 would use for on-screen doodles (frameless, stays-on-top tool
window, ``WindowTransparentForInput``, ``WA_TranslucentBackground``,
``WA_ShowWithoutActivating``; ``setScreen(s)`` + ``setGeometry(s.geometry())`` +
``showFullScreen()``) with a magenta 200x200 square at (100, 100), then:

- prints ``geometry()``, ``screen()``, ``isVisible()``, ``windowHandle()`` straight after
  ``showFullScreen()``, at the first Expose / show event, and after 100 ms (Q6)
- after 500 ms prints ``isActiveWindow()`` and ``focusWindow()`` (Q5 focus), takes one
  portal screenshot, and prints the average RGB inside the square and in a 50x50 control
  area, plus where magenta pixels were found (Q5 visible, Q6 offset)

    .venv-1/bin/python -I plans/phase-3/spike/layer_probe.py [--timeout 20]
    .venv-1/bin/python -I plans/phase-3/spike/layer_probe.py --hide-delay 150   # Q10
    .venv-1/bin/python -I plans/phase-3/spike/layer_probe.py --hold 10          # click test

``--hide-delay N``: show for 500 ms, ``hide()``, wait N ms, then shoot (Q10).
``--hold S``: show the square for S seconds, no screenshot (for your click test).
``--no-fullscreen``: ``show()`` at the screen's size instead of ``showFullScreen()``.
``--selector-fill``: also paint RegionSelector's dim colour over the whole layer, to see
what the region selector looks like on this desktop.

Without ``--hide-delay`` or ``--hold``, a second shot with the layer hidden is the
baseline: six control spots outside the square show whether the layer is see-through.

The screenshot is read into memory and its file deleted after the same checks as
``portal_shot.py``. Never saves or prints image data. Imports nothing from ``kami``.
"""

from __future__ import annotations

import argparse
import os
import secrets
import stat
import sys
import time
from urllib.parse import unquote, urlsplit

from PySide6.QtCore import SLOT, QEvent, QObject, QRect, Qt, QTimer, Slot
from PySide6.QtDBus import QDBusConnection, QDBusMessage, QDBusPendingCallWatcher
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget

DESKTOP = "org.freedesktop.portal.Desktop"
DESKTOP_PATH = "/org/freedesktop/portal/desktop"
REQUEST = "org.freedesktop.portal.Request"
MAX_BYTES = 64 * 1024 * 1024
EXIT_TIMEOUT = 3
SQUARE = QRect(100, 100, 200, 200)  # window-local, so screen-local if the window fills it
CONTROL = QRect(350, 100, 50, 50)   # outside the square
CONTROLS = [  # more spots outside the square, to see whether the layer is transparent there
    QRect(350, 100, 50, 50), QRect(1500, 100, 50, 50), QRect(100, 800, 50, 50),
    QRect(935, 515, 50, 50), QRect(1500, 900, 50, 50), QRect(700, 300, 50, 50),
]
MAGENTA = QColor("#FF00FF")
SELECTOR_FILL = QColor(30, 27, 46, 90)  # ui/region_select.py's dimming colour


def say(*parts: object) -> None:
    print(*parts, flush=True)


# --- the portal screenshot (same rules as portal_shot.py) -----------------------------


def checked_path(uri: str) -> tuple[str | None, str]:
    parts = urlsplit(uri)
    if parts.scheme != "file":
        return None, "not a file uri"
    if parts.netloc not in ("", "localhost"):
        return None, "remote host"
    path = unquote(parts.path)
    if not os.path.isabs(path):
        return None, "relative path"
    try:
        st = os.lstat(path)
    except OSError:
        return None, "lstat failed"
    if not stat.S_ISREG(st.st_mode):
        return None, "not a regular file"
    return path, ""


def read_and_delete(path: str) -> tuple[bytes | None, str]:
    data: bytes | None = None
    problem = ""
    try:
        before = os.lstat(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None, "not deleted (open failed)"
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return None, "not deleted (fstat: not a regular file)"
        if (st.st_dev, st.st_ino) != (before.st_dev, before.st_ino):
            return None, "not deleted (file changed)"
        chunks: list[bytes] = []
        total = 0
        while total <= MAX_BYTES:
            chunk = os.read(fd, min(1 << 20, MAX_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        if total > MAX_BYTES:
            problem = " (too big, not used)"
        else:
            data = b"".join(chunks)
    except OSError:
        problem = " (read failed)"
    finally:
        os.close(fd)
    try:
        os.unlink(path)
        deleted = True
    except FileNotFoundError:
        deleted = True
    except OSError:
        deleted = False
    return data, f"deleted {deleted}{problem}"


class PortalShot(QObject):
    """One non-interactive Screenshot. Calls ``done(data_or_None, status)`` exactly once."""

    def __init__(self, timeout_ms: int, done) -> None:
        super().__init__()
        self.bus = QDBusConnection.sessionBus()
        self.done = done
        self.token = "kami_spike_" + secrets.token_hex(4)
        name = self.bus.baseService().lstrip(":").replace(".", "_")
        self.path = f"{DESKTOP_PATH}/request/{name}/{self.token}"
        self.finished = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.on_timeout)
        self.timeout_ms = timeout_ms
        self.started = 0.0
        self.watcher: QDBusPendingCallWatcher | None = None

    def start(self) -> None:
        self.bus.connect(DESKTOP, self.path, REQUEST, "Response", self,
                         SLOT("on_response(uint,QVariantMap)"))
        msg = QDBusMessage.createMethodCall(
            DESKTOP, DESKTOP_PATH, "org.freedesktop.portal.Screenshot", "Screenshot"
        )
        msg.setArguments(["", {"handle_token": self.token, "interactive": False}])
        self.started = time.monotonic()
        self.watcher = QDBusPendingCallWatcher(self.bus.asyncCall(msg, self.timeout_ms), self)
        self.watcher.finished.connect(self.on_call_done)
        self.timer.start(self.timeout_ms)

    def on_call_done(self, watcher: QDBusPendingCallWatcher) -> None:
        reply = watcher.reply()
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            self.finish(None, f"call failed ({reply.errorName()})")

    @Slot("uint", "QVariantMap")
    def on_response(self, code: int, results: dict) -> None:
        ms = (time.monotonic() - self.started) * 1000
        uri = results.get("uri")
        if code != 0 or not isinstance(uri, str):
            self.finish(None, f"response {code} after {ms:.0f} ms")
            return
        path, why = checked_path(uri)
        if path is None:
            self.finish(None, f"response 0 after {ms:.0f} ms; not deleted ({why})")
            return
        data, status = read_and_delete(path)
        self.finish(data, f"response 0 after {ms:.0f} ms; {status}")

    def on_timeout(self) -> None:
        self.bus.send(QDBusMessage.createMethodCall(DESKTOP, self.path, REQUEST, "Close"))
        self.finish(None, "TIMEOUT (a dialog probably appeared); sent Request.Close")

    def finish(self, data: bytes | None, status: str) -> None:
        if self.finished:
            return
        self.finished = True
        self.timer.stop()
        self.bus.disconnect(DESKTOP, self.path, REQUEST, "Response", self,
                            SLOT("on_response(uint,QVariantMap)"))
        self.done(data, status)


# --- the layer ---------------------------------------------------------------------------


class Layer(QWidget):
    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.shown_at = 0.0
        self.first_show = True
        self.selector_fill = False

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        if self.selector_fill:  # what RegionSelector paints over the whole screen
            p.fillRect(self.rect(), SELECTOR_FILL)
        p.fillRect(SQUARE, MAGENTA)
        p.end()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.first_show:
            self.first_show = False
            report(self, f"(b) showEvent, {elapsed(self)}")


class ExposeWatch(QObject):
    """Event filter on the QWindow: reports the first Expose."""

    def __init__(self, layer: Layer) -> None:
        super().__init__()
        self.layer = layer
        self.seen = False

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Expose and not self.seen:
            self.seen = True
            exposed = obj.isExposed()
            report(self.layer, f"(b) first Expose, {elapsed(self.layer)}, isExposed {exposed}")
        return False


def elapsed(layer: Layer) -> str:
    return f"{(time.monotonic() - layer.shown_at) * 1000:.0f} ms after show"


def report(w: QWidget, when: str) -> None:
    g = w.geometry()
    s = w.screen()
    sg = s.geometry() if s is not None else None
    handle = w.windowHandle()
    say(f"{when}: geometry ({g.x()}, {g.y()}) {g.width()}x{g.height()}; "
        f"screen {s.name() if s else None}"
        + (f" ({sg.x()}, {sg.y()}) {sg.width()}x{sg.height()}" if sg else "")
        + f"; geometry == screen geometry {sg is not None and g == sg}; "
        f"isVisible {w.isVisible()}; windowHandle {'yes' if handle else 'None'}"
        + (f", exposed {handle.isExposed()}" if handle else ""))


def mean_rgb(image: QImage, rect: QRect) -> tuple[int, int, int]:
    r = g = b = n = 0
    step = 4
    for y in range(rect.top(), rect.bottom() + 1, step):
        for x in range(rect.left(), rect.right() + 1, step):
            c = image.pixelColor(x, y)
            r, g, b, n = r + c.red(), g + c.green(), b + c.blue(), n + 1
    return (r // n, g // n, b // n) if n else (-1, -1, -1)


def square_detail(image: QImage, rect: QRect) -> str:
    """Share of magenta-like pixels in the square, and its 3 commonest colours (/32)."""
    counts: dict[tuple[int, int, int], int] = {}
    like = n = 0
    for y in range(rect.top(), rect.bottom() + 1, 2):
        for x in range(rect.left(), rect.right() + 1, 2):
            c = image.pixelColor(x, y)
            n += 1
            if c.red() > 150 and c.blue() > 150 and c.green() < 90:
                like += 1
            key = (c.red() // 32 * 32, c.green() // 32 * 32, c.blue() // 32 * 32)
            counts[key] = counts.get(key, 0) + 1
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:3]
    tops = ", ".join(f"{rgb} {100 * cnt / n:.0f}%" for rgb, cnt in top)
    mid = rect.center().y()
    row = [image.pixelColor(x, mid) for x in range(rect.left(), rect.right() + 1, 25)]
    cells = " ".join(f"({c.red()},{c.green()},{c.blue()})" for c in row)
    return (f"magenta-like {100 * like / n:.0f}% of the square; commonest {tops}; "
            f"middle row every 25 px: {cells}")


def magenta_spread(image: QImage, square: QRect) -> str:
    """Near-magenta samples (every 4th pixel) inside and outside the square."""
    inside = outside = 0
    for y in range(0, image.height(), 4):
        for x in range(0, image.width(), 4):
            c = image.pixelColor(x, y)
            if c.red() > 230 and c.green() < 30 and c.blue() > 230:
                if square.contains(x, y):
                    inside += 1
                else:
                    outside += 1
    return f"near-magenta samples: {inside} inside the square, {outside} outside it"


def scaled(rect: QRect, k: float) -> QRect:
    return QRect(round(rect.x() * k), round(rect.y() * k),
                 round(rect.width() * k), round(rect.height() * k))


def control_means(image: QImage, k: float) -> list[tuple[int, int, int]]:
    return [mean_rgb(image, scaled(r, k)) for r in CONTROLS]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--timeout", type=float, default=20.0, help="seconds (20)")
    ap.add_argument("--hide-delay", type=int, default=None, metavar="MS")
    ap.add_argument("--hold", type=float, default=None, metavar="S")
    ap.add_argument("--no-fullscreen", action="store_true",
                    help="show() at the screen's size instead of showFullScreen()")
    ap.add_argument("--selector-fill", action="store_true",
                    help="also paint RegionSelector's dim fill over the whole layer")
    opts = ap.parse_args()

    app = QApplication(sys.argv)
    say(f"platform {QGuiApplication.platformName()}")
    screen = QGuiApplication.primaryScreen()
    say(f"target screen {screen.name()}, {len(QGuiApplication.screens())} screen(s)")
    layer = Layer()
    layer.selector_fill = opts.selector_fill
    watch = ExposeWatch(layer)
    exit_code = [0]
    shown: dict[str, list] = {}
    keep: list[PortalShot] = []  # the baseline shot must outlive its timer
    how = "show()" if opts.no_fullscreen else "showFullScreen()"

    layer.setScreen(screen)
    layer.setGeometry(screen.geometry())
    layer.shown_at = time.monotonic()
    if opts.no_fullscreen:
        layer.show()
    else:
        layer.showFullScreen()
    handle = layer.windowHandle()
    if handle is not None:
        handle.installEventFilter(watch)
        say(f"window format alpha buffer size {handle.format().alphaBufferSize()}")
    report(layer, f"(a) straight after {how}")
    QTimer.singleShot(100, lambda: report(layer, "(c) 100 ms single-shot"))

    def analyse(data: bytes | None, status: str, label: str) -> QImage | None:
        say(f"{label} screenshot: {status}")
        if status.startswith("TIMEOUT"):
            exit_code[0] = EXIT_TIMEOUT
        if data is None:
            return None
        image = QImage.fromData(data)
        del data
        return image

    def on_baseline(data: bytes | None, status: str) -> None:
        image = analyse(data, status, "baseline (layer hidden)")
        if image is not None and shown:
            k = image.width() / screen.geometry().width()
            hidden = control_means(image, k)
            say("control spots, layer shown -> hidden:")
            for rect, a, b in zip(CONTROLS, shown["controls"], hidden, strict=True):
                say(f"  ({rect.x()}, {rect.y()}): {a} -> {b}")
            black = sum(1 for a in shown["controls"] if a == (0, 0, 0))
            changed = sum(1 for a, b in zip(shown["controls"], hidden, strict=True)
                          if max(abs(x - y) for x, y in zip(a, b, strict=True)) > 8)
            say(f"spots pure black while shown: {black}/{len(CONTROLS)}; "
                f"spots that changed when hidden: {changed}/{len(CONTROLS)}")
            say(f"transparent outside the square: {changed == 0}")
            del image
        QTimer.singleShot(0, app.quit)

    def on_shot(data: bytes | None, status: str) -> None:
        image = analyse(data, status, "layer shown" if opts.hide_delay is None else
                        f"{opts.hide_delay} ms after hide()")
        got_image = image is not None
        if image is not None:
            k = image.width() / screen.geometry().width()
            say(f"image {image.width()}x{image.height()}, scale k = {k:.3f}")
            sq = scaled(SQUARE, k)
            inside = mean_rgb(image, sq)
            say(f"square mean RGB {inside}; control mean RGB {mean_rgb(image, scaled(CONTROL, k))}")
            say(square_detail(image, sq))
            say(magenta_spread(image, sq))
            say(f"square visible in the shot: "
                f"{inside[0] > 230 and inside[1] < 30 and inside[2] > 230}")
            if opts.hide_delay is None:
                shown["controls"] = control_means(image, k)
            del image
        if opts.hide_delay is None and got_image:
            layer.hide()
            say("hidden; baseline shot in 300 ms")
            keep.append(PortalShot(int(opts.timeout * 1000), on_baseline))
            QTimer.singleShot(300, keep[-1].start)
            return
        QTimer.singleShot(0, app.quit)

    shot = PortalShot(int(opts.timeout * 1000), on_shot)

    def at_500ms() -> None:
        report(layer, "(d) 500 ms")
        focus = QGuiApplication.focusWindow()
        say(f"isActiveWindow {layer.isActiveWindow()}; focusWindow "
            f"{'the layer' if focus is layer.windowHandle() else focus}")
        if opts.hold is not None:
            say(f"holding the square for {opts.hold:g} s: click a window under it now")
            QTimer.singleShot(int(opts.hold * 1000), app.quit)
        elif opts.hide_delay is not None:
            layer.hide()
            say(f"hidden; isVisible {layer.isVisible()}; shooting in {opts.hide_delay} ms")
            QTimer.singleShot(opts.hide_delay, shot.start)
        else:
            shot.start()

    QTimer.singleShot(500, at_500ms)
    app.exec()
    if handle is not None:
        handle.removeEventFilter(watch)
    return exit_code[0]


if __name__ == "__main__":
    sys.exit(main())
