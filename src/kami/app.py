"""Entry point.

    kami          start Kami (or toggle it if it's already running)
    kami toggle   show/hide the running Kami (bind this to a desktop shortcut)
"""
from __future__ import annotations

import logging
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from kami import __version__
from kami.config import ConfigError, load_config
from kami.hotkey import HotkeyListener
from kami.logs import remember_secret, setup_logging
from kami.ui.overlay import KamiOverlay

SOCKET_NAME = f"kami-{os.getuid()}"

log = logging.getLogger("kami")


def _send_toggle() -> bool:
    """Ask an already-running Kami to toggle. Returns True if one answered."""
    socket = QLocalSocket()
    socket.connectToServer(SOCKET_NAME)
    if not socket.waitForConnected(300):
        return False
    socket.write(b"toggle")
    socket.waitForBytesWritten(300)
    socket.disconnectFromServer()
    return True


def _tray_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#FF6B9A"))
    p.setPen(QColor("#1E1B2E"))
    p.drawEllipse(4, 4, 56, 56)
    p.end()
    return QIcon(pixmap)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    log_path = setup_logging()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Kami")
    app.setQuitOnLastWindowClosed(False)

    if _send_toggle():          # already running: just toggle it
        return 0
    if argv[:1] == ["toggle"]:
        print("Kami isn't running. Start it with: kami")
        return 1

    log.info("kami %s starting, session=%s", __version__,
             os.environ.get("XDG_SESSION_TYPE", "unknown"))
    try:
        config = load_config()
    except ConfigError as exc:
        log.error("config error: %s", exc)
        print(f"Kami can't start: {exc}", file=sys.stderr)
        QMessageBox.critical(None, "Kami can't start", str(exc))
        return 2
    remember_secret(config.llm.api_key)
    for warning in config.warnings:
        log.warning("config warning: %s", warning)  # stderr handler prints it too
    overlay = KamiOverlay(config)

    QLocalServer.removeServer(SOCKET_NAME)  # clean up a stale socket after a crash
    server = QLocalServer()
    server.listen(SOCKET_NAME)

    def on_connection() -> None:
        conn = server.nextPendingConnection()
        def on_ready() -> None:
            conn.readAll()
            overlay.toggle()

        conn.readyRead.connect(on_ready)

    server.newConnection.connect(on_connection)

    hotkey = HotkeyListener(config.hotkey)
    hotkey.triggered.connect(overlay.toggle)
    status = hotkey.start()
    log.info("model=%s hotkey: %s", config.llm.model, status)

    tray = QSystemTrayIcon(_tray_icon())
    menu = QMenu()
    show_action = QAction("Show Kami", menu)
    show_action.triggered.connect(overlay.summon)
    quit_action = QAction("Quit", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(show_action)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    tray.setToolTip(f"Kami: {status}")
    tray.activated.connect(lambda reason: overlay.toggle()
                           if reason == QSystemTrayIcon.Trigger else None)
    tray.show()

    print(f"Kami is running. {status}\nLogs: {log_path}")
    overlay.summon()
    code = app.exec()
    hotkey.stop()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
