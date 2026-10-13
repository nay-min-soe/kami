"""Global hotkey.

Which way Kami listens comes from `session.py` (`Session.hotkey`), decided once at
start-up; this module never reads the environment itself.

X11 (`"pynput"`): built-in listener via the optional `pynput` extra
(pip install 'kami[hotkey]').
Wayland (`"portal"`): apps can't grab global keys, so for now Kami shows
`hotkey_fallback_message` and you bind a desktop shortcut to `kami toggle`.
That command talks to the running Kami through a local socket (see app.py).
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from kami.session import Session, hotkey_fallback_message


class HotkeyListener(QObject):
    triggered = Signal()

    def __init__(self, combo: str, session: Session) -> None:
        super().__init__()
        self.combo = combo
        self.session = session
        self._listener = None

    def start(self) -> str:
        if self.session.hotkey == "portal":
            return hotkey_fallback_message(self.session)
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
