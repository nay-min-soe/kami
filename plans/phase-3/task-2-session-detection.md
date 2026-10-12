# Task 2 — Session detection in one place

**Size:** S · **Depends on:** — · **Branch:** `session-detection` · **Owner:** both · **Status:** ✅ built (commits `24b08e2`, `82526c1`, `2fa5b30`)

## Goal

Kami decides **once**, at start-up, what kind of desktop it runs on and what it can do
there. Every other part of Kami asks that one answer instead of reading environment
variables itself. `kami doctor` shows it as `Session ✓ wayland · gnome`.

## Why

- `XDG_SESSION_TYPE` is read in four places: `hotkey.py:23`, `app.py:65`, and
  `doctor.py`'s `check_session`, `check_hotkey` and `check_screen_grab`. Nothing reads
  `XDG_CURRENT_DESKTOP`, so Kami can't tell GNOME from KDE, and Tasks 3–6 need that.
- `overlay.CAPTURE_FAILED` hard-codes the Wayland advice, even on X11.
- `XDG_SESSION_TYPE` can be missing or `tty` (some `ssh -X` shells, some display
  managers, `sudo`). `WAYLAND_DISPLAY` and `DISPLAY` say more there.
- On a Wayland session where Qt runs on XWayland (`QT_QPA_PLATFORM=xcb`), Kami still
  can't grab other apps' windows (Task 1, Q9). So "the session is Wayland" and "Qt is on
  X11" are separate facts.

## Design

- New core module `src/kami/session.py`, with no Qt, so CI tests it. It is added to the
  core list in `ARCHITECTURE.md`.
- **Order of evidence:**
  1. `XDG_SESSION_TYPE`, trimmed and lowercased, only if it is `x11` or `wayland`.
  2. Otherwise `WAYLAND_DISPLAY` non-empty → `wayland`.
  3. Otherwise `DISPLAY` non-empty → `x11`.
  4. Otherwise `unknown`.
- **Desktop:** `XDG_CURRENT_DESKTOP` is a colon list (`ubuntu:GNOME`, `KDE`, `sway`,
  `Hyprland`). Split it on `:`, lowercase each part, and use the first part that is one
  of `gnome`, `kde`, `sway`, `hyprland`. If none matches (or the variable is missing),
  the desktop is `other`.
- **XWayland:** only on a `wayland` session. The platform is `qt_platform` when it's
  given (`QGuiApplication.platformName()`, passed in by `app.py`), otherwise the first
  `;`-separated entry of `QT_QPA_PLATFORM` from `env` (`doctor.py` passes no
  `qt_platform`). `xwayland` is `True` when that platform starts with `xcb`.
- **Choices:**
  - `capture` is `"portal"` on a `wayland` session (with or without XWayland), and
    `"x11"` otherwise. `unknown` tries `grabWindow`, as today.
  - `hotkey` is `"portal"` on `wayland` and `"pynput"` otherwise. `"portal"` is only a
    *candidate*: Task 6 checks at runtime that the portal exists.
- **Messages move to core.** These used to be inline in the UI:
  - `capture_failed_message(session)`: on Wayland it's today's `CAPTURE_FAILED` text,
    word for word (Task 3 replaces it). On X11 / unknown it's *"Kami couldn't capture
    your screen. Run `kami doctor` to see why."*
  - `hotkey_fallback_message(session)`: on Wayland it's today's text, *"Wayland session:
    bind a desktop shortcut to `kami toggle`."* Task 6 makes it name the desktop.
- **Logging:** `app.py` logs once at start: `kami 0.1.0 starting, session kind=wayland
  desktop=gnome xwayland=no`. It replaces today's `session=%s` line. There's nothing
  private in it.
- **Known limit:** detection runs once. Switching session type needs a restart of Kami
  anyway (you log out).

## Contract

backend-dev builds this; frontend-dev calls it.

```python
# src/kami/session.py  (new, core: no Qt)
from collections.abc import Mapping
from dataclasses import dataclass

@dataclass(frozen=True)
class Session:
    kind: str              # "x11" | "wayland" | "unknown"
    desktop: str           # "gnome" | "kde" | "sway" | "hyprland" | "other"
    xwayland: bool = False # Wayland session, but Qt runs on xcb

    @property
    def capture(self) -> str: ...   # "x11" | "portal"
    @property
    def hotkey(self) -> str: ...    # "pynput" | "portal"
    def describe(self) -> str: ...  # "wayland · gnome", "wayland · gnome · xwayland", "unknown · other"
    def log_fields(self) -> str: ...  # "kind=wayland desktop=gnome xwayland=no"

def detect(env: Mapping[str, str], qt_platform: str | None = None) -> Session: ...
def capture_failed_message(session: Session) -> str: ...
def hotkey_fallback_message(session: Session) -> str: ...
```

Frontend side (UI-internal, but both halves must agree):

- `KamiOverlay(config: Config, session: Session)`. It keeps the session as
  `self.session`.
- `HotkeyListener(combo: str, session: Session)`. It keeps the session as
  `self.session`.
- `detect()` never raises. A bad or empty environment gives `Session("unknown", "other")`.

## Backend part (backend-dev)

| File | Change |
|---|---|
| `src/kami/session.py` | new: the Contract |
| `src/kami/doctor.py` | `check_session`, `check_hotkey` and `check_screen_grab` use `detect(env)` instead of `env.get("XDG_SESSION_TYPE")` |
| `tests/test_session.py` | new |
| `tests/test_doctor.py` | one new test for the unknown session row; existing tests unchanged |
| `ARCHITECTURE.md` | `session.py` box in Core, `session.py` in "The one rule for layers" |

Steps:

1. Write `tests/test_session.py` (below) first, then `session.py` to make it pass.
2. `doctor.check_session(env)`: `s = detect(env)`. For `unknown`, return
   `Check("Session", "warn", "unknown (no XDG_SESSION_TYPE, WAYLAND_DISPLAY or DISPLAY)")`.
   Otherwise return `Check("Session", "ok", s.describe())`.
3. `doctor.check_hotkey(env, combo)`: replace the `env.get(...) == "wayland"` test with
   `detect(env).kind == "wayland"`. The messages stay word for word (Task 6 changes them).
4. `doctor.check_screen_grab(env)`: branch on `detect(env).kind`, with the same three
   messages as today.
5. Run `grep -rn XDG_SESSION_TYPE src/`. After frontend-dev's part, only `session.py`
   may match.
6. `.venv-1/bin/python -m pytest -q` and `.venv-1/bin/ruff check .`.

## Frontend part (frontend-dev)

| File | Change |
|---|---|
| `src/kami/app.py` | `detect(os.environ, app.platformName())` once, after `QApplication` exists. Log `session.log_fields()`. Pass the session to `KamiOverlay` and `HotkeyListener` |
| `src/kami/hotkey.py` | `__init__(combo, session)`; `start()` branches on `self.session.hotkey == "portal"` and returns `hotkey_fallback_message(self.session)`. Drop `import os` |
| `src/kami/ui/overlay.py` | `__init__(config, session)`; delete `CAPTURE_FAILED`; the empty-capture branch shows `capture_failed_message(self.session)` |

Steps:

1. In `app.py` `main()`, right after `app.setQuitOnLastWindowClosed(False)` and the
   `_send_toggle` / `toggle` early returns, call
   `session = detect(os.environ, app.platformName())`.
2. Replace the `log.info("kami %s starting, session=%s", …)` call with
   `log.info("kami %s starting, session %s", __version__, session.log_fields())`.
3. Change `KamiOverlay(config)` to `KamiOverlay(config, session)`, and
   `HotkeyListener(config.hotkey)` to `HotkeyListener(config.hotkey, session)`.
4. In `hotkey.py`, the pynput path (import, `GlobalHotKeys`, `start()`) stays exactly as
   it is.
5. In `overlay.py`, only the message line in `_capture_region`'s empty branch changes. The
   X11 grab code stays as it is.
6. Update `hotkey.py`'s module docstring to say the choice comes from `session.py`.

## Tests

- [x] `test_x11_from_session_type` / `test_wayland_from_session_type` in `tests/test_session.py`
- [x] `test_session_type_is_trimmed_and_lowercased` (`" Wayland "` → wayland)
- [x] `test_tty_session_type_falls_through_to_display`
- [x] `test_falls_back_to_wayland_display`: no `XDG_SESSION_TYPE`, `WAYLAND_DISPLAY` set → wayland
- [x] `test_falls_back_to_display`: only `DISPLAY` → x11
- [x] `test_nothing_set_is_unknown`: `{}` → `Session("unknown", "other")`, `capture == "x11"`
- [x] `test_desktop_names`: `ubuntu:GNOME` → gnome, `KDE` → kde, `sway`, `Hyprland`, `XFCE` → other, missing → other
- [x] `test_xwayland_from_qt_platform`: wayland + `qt_platform="xcb"` → `xwayland=True`, `capture == "portal"`, `hotkey == "portal"`
- [x] `test_xwayland_from_env_when_no_qt_platform`: `QT_QPA_PLATFORM="xcb;wayland"` → `xwayland=True`
- [x] `test_xwayland_only_on_wayland`: x11 + `qt_platform="xcb"` → `xwayland=False`
- [x] `test_capture_and_hotkey_choices`: x11 → (`x11`, `pynput`); wayland → (`portal`, `portal`)
- [x] `test_describe_and_log_fields`
- [x] `test_capture_failed_message_wayland_keeps_old_text` / `test_capture_failed_message_x11_points_to_doctor`
- [x] `test_hotkey_fallback_message_wayland_keeps_old_text` (word for word: *"Wayland session: bind a desktop shortcut to `kami toggle`."*)
- [x] `test_doctor_unknown_session_warns` in `tests/test_doctor.py`
- [x] Existing `tests/test_doctor.py` tests pass unchanged

## Manual check

Builder, on this machine (no clicks):

- [x] `.venv-1/bin/python -m kami doctor` shows `Session ✓ wayland · gnome`
- [x] `env -u XDG_SESSION_TYPE .venv-1/bin/python -m kami doctor` still shows `wayland · gnome`
      (from `WAYLAND_DISPLAY`)
- [x] Doctor's `Running` row says "not running" (if your own Kami is running, starting
      another one would only toggle yours, so skip this check). Then run
      `timeout 20 .venv-1/bin/python -m kami; grep "session kind" ~/.local/state/kami/kami.log | tail -1`.
      It shows `kind=wayland desktop=gnome xwayland=no`
- [x] Same with `QT_QPA_PLATFORM=xcb` in front: `xwayland=yes`

Yours (in `your-checklist.md`):

- [ ] X11 ("Ubuntu on Xorg"): the pynput hotkey still toggles the panel, and doctor shows
      `x11 · gnome`

## Security

None. The task reads environment variables and logs only the session kind, desktop and
a yes/no.

## Done when

- [x] `XDG_SESSION_TYPE` is read only in `src/kami/session.py` (`grep` also finds it in
      `doctor.py`, but only inside the unknown-session row's text)
- [x] `kami doctor` shows `Session ✓ wayland · gnome` on this machine
- [x] X11 behaviour is unchanged: same hotkey path, same doctor messages (existing tests
      green)
- [x] 169 + the new tests pass (202 on 2026-10-13), and ruff is clean

## Commits

1. `add session detection`
2. `use session detection in doctor`
3. `use session detection in hotkey and panel`
