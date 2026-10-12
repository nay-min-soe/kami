"""Phase 3 spike, Q1-Q4 and Q11: one call to the Screenshot portal, measured.

    .venv-1/bin/python -I plans/phase-3/spike/portal_shot.py [--timeout 20] [--layout]
    .venv-1/bin/python -I plans/phase-3/spike/portal_shot.py --interactive --timeout 120

What it does, once (no retries):

1. Reads the permission store's ``screenshot`` table.
2. Builds the request path from the bus's unique name and a fresh token, and connects
   ``Response`` on that path, from ``org.freedesktop.portal.Desktop`` only, **before**
   calling ``Screenshot``. Two slots listen: a typed ``(uint, QVariantMap)`` one and a
   ``QDBusMessage`` one, so Q1 sees which style works.
3. Calls ``Screenshot("", {handle_token, interactive})`` asynchronously.
4. On ``Response``: prints the code, the result keys and their Python types, the URI's
   scheme and **directory** (never the file name), then reads the PNG into memory and
   deletes it, after the checks Kami will use (file scheme, empty / localhost host,
   absolute path, lstat and fstat say regular file). ``--layout`` decodes the bytes and
   prints the image size next to every screen.
5. On timeout: calls ``Request.Close`` (which closes any dialog), prints
   ``TIMEOUT (a dialog probably appeared)`` and exits 3.

Never saves or prints image data. Imports nothing from ``kami``.
"""

from __future__ import annotations

import argparse
import os
import secrets
import stat
import sys
import time
from urllib.parse import unquote, urlsplit

from PySide6.QtCore import SLOT, QCoreApplication, QObject, QTimer, Slot
from PySide6.QtDBus import (
    QDBus,
    QDBusConnection,
    QDBusMessage,
    QDBusPendingCall,
    QDBusPendingCallWatcher,
)

DESKTOP = "org.freedesktop.portal.Desktop"
DESKTOP_PATH = "/org/freedesktop/portal/desktop"
REQUEST = "org.freedesktop.portal.Request"
MAX_BYTES = 64 * 1024 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
EXIT_TIMEOUT = 3


def say(*parts: object) -> None:
    print(*parts, flush=True)


def request_path(unique_name: str, token: str) -> str:
    return f"{DESKTOP_PATH}/request/{unique_name.lstrip(':').replace('.', '_')}/{token}"


def permission_store(bus: QDBusConnection) -> str:
    msg = QDBusMessage.createMethodCall(
        "org.freedesktop.impl.portal.PermissionStore",
        "/org/freedesktop/impl/portal/PermissionStore",
        "org.freedesktop.impl.portal.PermissionStore",
        "List",
    )
    msg.setArguments(["screenshot"])
    reply = bus.call(msg, QDBus.CallMode.Block, 2000)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        return f"error {reply.errorName()}"
    return repr(reply.arguments()[0] if reply.arguments() else None)


def show_dir(path: str) -> str:
    """The file's directory, with $HOME shortened to ~. Never the file name."""
    folder = os.path.dirname(path)
    home = os.path.expanduser("~")
    if folder == home or folder.startswith(home + os.sep):
        folder = "~" + folder[len(home):]
    return folder + "/"


def checked_path(uri: str) -> tuple[str | None, str]:
    """The four checks before Kami may touch the file. Returns (path, "") or (None, why)."""
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
    """Read at most MAX_BYTES + 1 bytes, then unlink. Returns (data, status line)."""
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


def type_tree(value: object) -> str:
    if isinstance(value, dict):
        return "dict{" + ", ".join(f"{k!r}: {type_tree(v)}" for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return type(value).__name__ + "[" + ", ".join(type_tree(v) for v in value) + "]"
    return type(value).__name__


class Shot(QObject):
    """One Screenshot request: subscribe first, call, wait for Response or the timeout."""

    def __init__(self, app: QCoreApplication, interactive: bool, timeout_ms: int) -> None:
        super().__init__()
        self.app = app
        self.bus = QDBusConnection.sessionBus()
        self.interactive = interactive
        self.timeout_ms = timeout_ms
        self.token = "kami_spike_" + secrets.token_hex(4)
        self.path = request_path(self.bus.baseService(), self.token)
        self.code: int | None = None
        self.results: dict = {}
        self.typed_fired = False
        self.message_fired = False
        self.exit_code = 1
        self.started = 0.0
        self.elapsed_ms = 0.0
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.on_timeout)
        self.watcher: QDBusPendingCallWatcher | None = None

    def start(self) -> None:
        say(f"unique name {self.bus.baseService()}, predicted path …/request/"
            f"{self.bus.baseService().lstrip(':').replace('.', '_')}/{self.token}")
        ok_typed = self.bus.connect(DESKTOP, self.path, REQUEST, "Response", self,
                                    SLOT("on_typed(uint,QVariantMap)"))
        ok_msg = self.bus.connect(DESKTOP, self.path, REQUEST, "Response", self,
                                  SLOT("on_message(QDBusMessage)"))
        say(f"subscribed before the call: typed slot {ok_typed}, QDBusMessage slot {ok_msg}")
        msg = QDBusMessage.createMethodCall(
            DESKTOP, DESKTOP_PATH, "org.freedesktop.portal.Screenshot", "Screenshot"
        )
        msg.setArguments(["", {"handle_token": self.token, "interactive": self.interactive}])
        self.started = time.monotonic()
        pending: QDBusPendingCall = self.bus.asyncCall(msg, self.timeout_ms)
        self.watcher = QDBusPendingCallWatcher(pending, self)
        self.watcher.finished.connect(self.on_call_done)
        self.timer.start(self.timeout_ms)

    def on_call_done(self, watcher: QDBusPendingCallWatcher) -> None:
        reply = watcher.reply()
        ms = (time.monotonic() - self.started) * 1000
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            say(f"Screenshot call failed: {reply.errorName()} ({ms:.0f} ms)")
            self.finish(1)
            return
        handle = reply.arguments()[0] if reply.arguments() else None
        returned = handle.path() if hasattr(handle, "path") else str(handle)
        say(f"Screenshot call returned a handle after {ms:.0f} ms "
            f"(type {type(handle).__name__}); same as predicted path: {returned == self.path}")

    @Slot("uint", "QVariantMap")
    def on_typed(self, code: int, results: dict) -> None:
        if self.typed_fired:
            return
        self.typed_fired = True
        self.elapsed_ms = (time.monotonic() - self.started) * 1000
        self.code = int(code)
        self.results = dict(results)
        say(f"typed slot (uint, QVariantMap) fired: code type {type(code).__name__}, "
            f"results {type_tree(self.results)}")
        QTimer.singleShot(0, self.handle_reply)  # let the other slot run too

    @Slot(QDBusMessage)
    def on_message(self, message: QDBusMessage) -> None:
        self.message_fired = True
        args = message.arguments()
        say(f"QDBusMessage slot fired: signature {message.signature()!r}, "
            f"arguments {[type(a).__name__ for a in args]}")

    def on_timeout(self) -> None:
        close = QDBusMessage.createMethodCall(DESKTOP, self.path, REQUEST, "Close")
        self.bus.send(close)  # closes any dialog the portal opened; no reply needed
        say(f"TIMEOUT (a dialog probably appeared) after {self.timeout_ms / 1000:.0f} s; "
            "sent Request.Close")
        self.finish(EXIT_TIMEOUT)

    def handle_reply(self) -> None:
        self.timer.stop()
        say(f"response {self.code} after {self.elapsed_ms:.0f} ms")
        keys = ", ".join(f"{k}: {type(v).__name__}" for k, v in sorted(self.results.items()))
        say(f"results keys: {keys or '(none)'}")
        say(f"slots that fired: typed {self.typed_fired}, QDBusMessage {self.message_fired}")
        uri = self.results.get("uri")
        if self.code != 0 or not isinstance(uri, str):
            self.finish(4 if self.code else 1)
            return
        parts = urlsplit(uri)
        path = unquote(parts.path)
        try:
            regular = stat.S_ISREG(os.lstat(path).st_mode)
        except OSError:
            regular = None
        say(f"uri scheme {parts.scheme!r}, host {parts.netloc!r}, directory {show_dir(path)}, "
            f"extension {os.path.splitext(path)[1]!r}, lstat regular file: {regular}")
        good, why = checked_path(uri)
        if good is None:
            say(f"not deleted ({why})")
            self.finish(1)
            return
        data, status = read_and_delete(good)
        say(status)
        say(f"file still there afterwards: {os.path.lexists(good)}")
        if data is not None:
            say(f"bytes {len(data)}, PNG signature: {data[:8] == PNG_MAGIC}")
            self.on_image(data)
        del data
        self.finish(0)

    def on_image(self, data: bytes) -> None:
        """Hook for --layout (needs a QGuiApplication)."""

    def finish(self, code: int) -> None:
        self.exit_code = code
        self.bus.disconnect(DESKTOP, self.path, REQUEST, "Response", self,
                            SLOT("on_typed(uint,QVariantMap)"))
        self.bus.disconnect(DESKTOP, self.path, REQUEST, "Response", self,
                            SLOT("on_message(QDBusMessage)"))
        QTimer.singleShot(0, self.app.quit)


class LayoutShot(Shot):
    def on_image(self, data: bytes) -> None:
        from PySide6.QtGui import QGuiApplication, QImage

        image = QImage.fromData(data)
        say(f"image {image.width()}x{image.height()} (null: {image.isNull()}, "
            f"depth {image.depth()})")
        for s in QGuiApplication.screens():
            g = s.geometry()
            dpr = s.devicePixelRatio()
            say(f"screen {s.name()}: geometry ({g.x()}, {g.y()}) {g.width()}x{g.height()}, "
                f"devicePixelRatio {dpr}, x dpr = {round(g.width() * dpr)}x"
                f"{round(g.height() * dpr)}")
        say(f"platform {QGuiApplication.platformName()}")
        del image


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--timeout", type=float, default=20.0, help="seconds (20)")
    ap.add_argument("--interactive", action="store_true", help="use the desktop's picker")
    ap.add_argument("--layout", action="store_true", help="decode and compare with screens")
    opts = ap.parse_args()

    if opts.layout:
        from PySide6.QtGui import QGuiApplication

        app: QCoreApplication = QGuiApplication(sys.argv)
    else:
        app = QCoreApplication(sys.argv)
    bus = QDBusConnection.sessionBus()
    say(f"permission store before: {permission_store(bus)}")
    cls = LayoutShot if opts.layout else Shot
    shot = cls(app, opts.interactive, int(opts.timeout * 1000))
    QTimer.singleShot(0, shot.start)
    app.exec()
    say(f"permission store after: {permission_store(bus)}")
    return shot.exit_code


if __name__ == "__main__":
    sys.exit(main())
