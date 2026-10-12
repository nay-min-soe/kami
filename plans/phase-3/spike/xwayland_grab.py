"""Phase 3 spike, Q9: what ``grabWindow(0, ...)`` returns under XWayland.

Must run with Qt on XWayland inside a Wayland session:

    QT_QPA_PLATFORM=xcb .venv-1/bin/python -I plans/phase-3/spike/xwayland_grab.py

It shows a small magenta window of its own (an X11 client), waits 500 ms, grabs the
whole primary screen the way ``_capture_region`` does, and prints the pixmap size,
``isNull()``, the share of pure-black pixels, the share of magenta ones (its own window)
and the share of anything else (other windows, the desktop). The grab stays in memory
and is dropped at once. Imports nothing from ``kami``.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QApplication, QWidget


def say(*parts: object) -> None:
    print(*parts, flush=True)


class Square(QWidget):
    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setGeometry(100, 100, 200, 200)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#FF00FF"))
        p.end()


def main() -> int:
    platform = os.environ.get("QT_QPA_PLATFORM", "")
    if not platform.startswith("xcb"):
        say("Run this with QT_QPA_PLATFORM=xcb (Qt on XWayland). "
            f"QT_QPA_PLATFORM is {platform!r}.")
        return 2
    if os.environ.get("XDG_SESSION_TYPE") != "wayland":
        say("This checks XWayland, so it only means something in a Wayland session.")

    app = QApplication(sys.argv)
    say(f"platform {QGuiApplication.platformName()}; "
        f"XDG_SESSION_TYPE {os.environ.get('XDG_SESSION_TYPE')}")
    square = Square()
    square.show()

    def grab() -> None:
        screen = QGuiApplication.primaryScreen()
        g = screen.geometry()
        pixmap = screen.grabWindow(0, g.x(), g.y(), g.width(), g.height())
        say(f"screen {screen.name()} ({g.x()}, {g.y()}) {g.width()}x{g.height()}, "
            f"dpr {screen.devicePixelRatio()}")
        say(f"pixmap {pixmap.width()}x{pixmap.height()}, isNull {pixmap.isNull()}")
        if not pixmap.isNull():
            image = pixmap.toImage()
            del pixmap
            black = magenta = other = 0
            for y in range(0, image.height(), 4):
                for x in range(0, image.width(), 4):
                    c = image.pixelColor(x, y)
                    if c.red() == c.green() == c.blue() == 0:
                        black += 1
                    elif c.red() > 230 and c.green() < 30 and c.blue() > 230:
                        magenta += 1
                    else:
                        other += 1
            total = black + magenta + other
            say(f"samples {total}: pure black {100 * black / total:.1f}%, "
                f"magenta (own window) {100 * magenta / total:.1f}%, "
                f"anything else {100 * other / total:.1f}%")
            del image
        app.quit()

    QTimer.singleShot(500, grab)
    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
