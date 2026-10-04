"""Global hotkey.

X11: built-in listener via the optional `pynput` extra (pip install 'kami[hotkey]').
Wayland: apps can't grab global keys, so bind a desktop shortcut to `kami toggle`.
That command talks to the running Kami through a local socket (see app.py).
"""
from __future__ import annotations

import os

from PySide6.QtCore import QObject, Signal


class HotkeyListener(QObject):
    triggered = Signal()

    def __init__(self, combo: str) -> None:
        super().__init__()
        self.combo = combo
        self._listener = None

    def start(self) -> str:
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            return "Wayland session: bind a desktop shortcut to `kami toggle`."
        try:
            from pynput import keyboard
        except ImportError:
            return "pynput not installed: pip install 'kami[hotkey]' or bind `kami toggle`."
        # pynput calls back on its own thread; the Qt signal queues it safely.
        self._listener = keyboard.GlobalHotKeys({self.combo: self.triggered.emit})
        self._listener.start()
        return f"Hotkey {self.combo} active."

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
