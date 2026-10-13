"""What kind of desktop Kami runs on, decided once at start-up. No Qt, so pytest covers it.

Every other module asks the `Session` from `detect()` instead of reading environment
variables itself. Evidence for the session kind, in order:

1. `XDG_SESSION_TYPE`, if it says `x11` or `wayland` (it can be missing or `tty` under
   `ssh -X`, `sudo` and some display managers).
2. `WAYLAND_DISPLAY` set → `wayland`.
3. `DISPLAY` set → `x11`.
4. Otherwise `unknown`, which behaves like X11 (Kami tries `grabWindow`, as before).

The desktop comes from `XDG_CURRENT_DESKTOP`. `xwayland` means a Wayland session where
Qt itself runs on xcb: Kami still can't grab other apps' windows there.

Detection runs once; switching session type means logging out, which restarts Kami.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

KINDS = ("x11", "wayland")
DESKTOPS = ("gnome", "kde", "sway", "hyprland")

CAPTURE_FAILED_WAYLAND = (
    "Kami couldn't capture your screen. On Wayland, screen capture isn't supported yet: "
    'log in with "Ubuntu on Xorg" (or "GNOME on Xorg") to use Explain screen.'
)
CAPTURE_FAILED_OTHER = "Kami couldn't capture your screen. Run `kami doctor` to see why."
HOTKEY_FALLBACK_WAYLAND = "Wayland session: bind a desktop shortcut to `kami toggle`."
HOTKEY_FALLBACK_OTHER = "Bind a desktop shortcut to `kami toggle`."


@dataclass(frozen=True)
class Session:
    kind: str               # "x11" | "wayland" | "unknown"
    desktop: str            # "gnome" | "kde" | "sway" | "hyprland" | "other"
    xwayland: bool = False  # Wayland session, but Qt runs on xcb

    @property
    def capture(self) -> str:
        """`"portal"` on Wayland (XWayland too), `"x11"` (grabWindow) otherwise."""
        return "portal" if self.kind == "wayland" else "x11"

    @property
    def hotkey(self) -> str:
        """`"portal"` on Wayland, `"pynput"` otherwise. The portal is only a candidate:
        whether it exists is checked at runtime."""
        return "portal" if self.kind == "wayland" else "pynput"

    def describe(self) -> str:
        """For `kami doctor`, e.g. `wayland · gnome · xwayland`."""
        parts = [self.kind, self.desktop] + (["xwayland"] if self.xwayland else [])
        return " · ".join(parts)

    def log_fields(self) -> str:
        """For the start-up log line. Nothing private in it."""
        return (f"kind={self.kind} desktop={self.desktop} "
                f"xwayland={'yes' if self.xwayland else 'no'}")


def _read(env: Mapping[str, str], name: str) -> str:
    """One variable, trimmed and lowercased; anything that isn't a string counts as unset."""
    value = env.get(name)
    return value.strip().lower() if isinstance(value, str) else ""


def _kind(env: Mapping[str, str]) -> str:
    session_type = _read(env, "XDG_SESSION_TYPE")
    if session_type in KINDS:
        return session_type
    if _read(env, "WAYLAND_DISPLAY"):
        return "wayland"
    if _read(env, "DISPLAY"):
        return "x11"
    return "unknown"


def _desktop(env: Mapping[str, str]) -> str:
    parts = (part.strip() for part in _read(env, "XDG_CURRENT_DESKTOP").split(":"))
    return next((part for part in parts if part in DESKTOPS), "other")


def _xwayland(env: Mapping[str, str], qt_platform: str | None) -> bool:
    if isinstance(qt_platform, str) and qt_platform.strip():
        platform = qt_platform.strip().lower()
    else:
        platform = _read(env, "QT_QPA_PLATFORM").split(";")[0].strip()
    return platform.startswith("xcb")


def detect(env: Mapping[str, str], qt_platform: str | None = None) -> Session:
    """The session from `env` (usually `os.environ`). `qt_platform` is
    `QGuiApplication.platformName()` when Qt is running; without it, `QT_QPA_PLATFORM`
    is used. Never raises: a bad or empty environment gives `Session("unknown", "other")`."""
    try:
        kind = _kind(env)
        desktop = _desktop(env)
        xwayland = kind == "wayland" and _xwayland(env, qt_platform)
    except Exception:  # an odd Mapping must not stop Kami from starting
        return Session("unknown", "other")
    return Session(kind, desktop, xwayland)


def capture_failed_message(session: Session) -> str:
    """Shown in the panel when a screen capture comes back empty."""
    return CAPTURE_FAILED_WAYLAND if session.kind == "wayland" else CAPTURE_FAILED_OTHER


def hotkey_fallback_message(session: Session) -> str:
    """Shown when Kami can't listen for the hotkey itself."""
    return HOTKEY_FALLBACK_WAYLAND if session.kind == "wayland" else HOTKEY_FALLBACK_OTHER
