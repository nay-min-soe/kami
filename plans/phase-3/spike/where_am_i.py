"""Phase 3 spike, Q7: what Qt knows about the cursor and the screen when Kami is summoned.

Run it from a terminal, the way ``kami toggle`` summons the panel: the cursor is not over
a Kami window. It does what ``KamiOverlay.summon()`` does (``screenAt(QCursor.pos())``,
``move()`` to the top-right of that screen, ``show()``, ``raise_()``,
``activateWindow()``) with a panel-sized window, keeps it up for 5 s, and prints
``QCursor.pos()``, ``screenAt()`` and the window's ``screen()`` before and after.

    .venv-1/bin/python -I plans/phase-3/spike/where_am_i.py [--seconds 5]

No screenshot, nothing written. Imports nothing from ``kami``.
"""

from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter
from PySide6.QtWidgets import QApplication, QWidget


def say(*parts: object) -> None:
    print(*parts, flush=True)


class Panel(QWidget):
    """Same window flags as KamiOverlay, painted opaque."""

    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(520, 460)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#1E1B2E"))
        p.setPen(QColor("white"))
        p.drawText(self.rect(), Qt.AlignCenter, "Kami spike: where am I? (closes in a moment)")
        p.end()


def cursor_line(when: str) -> None:
    pos = QCursor.pos()
    under = QGuiApplication.screenAt(pos)
    say(f"{when}: QCursor.pos() ({pos.x()}, {pos.y()}); "
        f"screenAt -> {under.name() if under else None}")


def window_line(when: str, w: QWidget) -> None:
    s = w.screen()
    g = w.geometry()
    say(f"{when}: window screen() {s.name() if s else None}; geometry ({g.x()}, {g.y()}) "
        f"{g.width()}x{g.height()}; isVisible {w.isVisible()}; "
        f"isActiveWindow {w.isActiveWindow()}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seconds", type=float, default=5.0)
    opts = ap.parse_args()

    app = QApplication(sys.argv)
    say(f"platform {QGuiApplication.platformName()}; primary "
        f"{QGuiApplication.primaryScreen().name()}; screens "
        + ", ".join(s.name() for s in QGuiApplication.screens()))
    cursor_line("before show")

    panel = Panel()
    here = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    avail = here.availableGeometry()
    target = (avail.right() - panel.width() - 24, avail.top() + 48)
    say(f"summon() picks screen {here.name()}, availableGeometry ({avail.x()}, {avail.y()}) "
        f"{avail.width()}x{avail.height()}, move{target}")
    panel.move(*target)
    panel.show()
    panel.raise_()
    panel.activateWindow()
    cursor_line("straight after show")
    window_line("straight after show", panel)

    QTimer.singleShot(300, lambda: (cursor_line("after 300 ms"),
                                    window_line("after 300 ms", panel)))

    def done() -> None:
        cursor_line(f"after {opts.seconds:g} s")
        window_line(f"after {opts.seconds:g} s", panel)
        app.quit()

    QTimer.singleShot(int(opts.seconds * 1000), done)
    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
