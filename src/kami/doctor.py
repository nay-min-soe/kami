"""`kami doctor`: a health report a user can paste into a bug report.

Rules: never print the API key (only where it came from), never send a chat request
(that costs money; the endpoint check uses the free GET /models), give every network
check a 5 s timeout, and never let one failed check stop the report.
No Qt at module level, so this works without a display.
"""
from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path

import httpx

from kami import __version__
from kami.config import API_KEY_ENV_VARS, CONFIG_PATH, Config, ConfigError, load_config
from kami.llm import LLMClient, LLMError
from kami.logs import default_state_dir

SYMBOLS = {"ok": "✓", "warn": "⚠", "fail": "✗", "info": "–"}
TIMEOUT = 5.0


@dataclass
class Check:
    name: str
    status: str  # "ok" | "warn" | "fail" | "info"
    detail: str


def check_session(env) -> Check:
    session = env.get("XDG_SESSION_TYPE", "")
    if not session:
        return Check("Session", "warn", "unknown (XDG_SESSION_TYPE is not set)")
    return Check("Session", "ok", f"{session} (XDG_SESSION_TYPE)")


def check_config(path: Path) -> tuple[list[Check], Config | None]:
    shown = str(path).replace(str(Path.home()), "~", 1)
    try:
        config = load_config(path)
    except ConfigError as exc:
        return [Check("Config", "fail", str(exc))], None
    state = "loaded" if path.exists() else "not found, using defaults"
    rows = [Check("Config", "ok", f"{shown}  {state}")]
    rows += [Check("", "warn", warning) for warning in config.warnings]
    return rows, config


def check_api_key(env, config: Config) -> Check:
    for name in API_KEY_ENV_VARS:
        if env.get(name, "").strip():
            return Check("API key", "ok", f"set (from {name})")
    if config.llm.api_key:
        return Check("API key", "ok", "set (from config.toml)")
    return Check("API key", "fail", "not set → export OPENROUTER_API_KEY=... "
                                    "(or KAMI_API_KEY, or api_key in config.toml)")


def check_endpoint_and_model(config: Config, http: httpx.Client | None) -> list[Check]:
    client = LLMClient(config.llm, timeout=TIMEOUT, http=http)
    try:
        models = client.list_models(timeout=TIMEOUT)
    except LLMError as exc:
        return [Check("Endpoint", "fail", f"{config.llm.base_url}  {exc}"),
                Check("Model", "info", f"{config.llm.model}  not checked")]
    rows = [Check("Endpoint", "ok", f"{config.llm.base_url}  reachable")]
    model = next((m for m in models if m.get("id") == config.llm.model), None)
    if model is None:
        rows.append(Check("Model", "warn", f"{config.llm.model}  not in the endpoint's "
                                           "model list. Check the name"))
        return rows
    inputs = (model.get("architecture") or {}).get("input_modalities")
    if not isinstance(inputs, list):
        rows.append(Check("Model", "ok", f"{config.llm.model}  listed · images: unknown"))
    elif "image" in inputs:
        rows.append(Check("Model", "ok", f"{config.llm.model}  listed · images: yes"))
    else:
        rows.append(Check("Model", "warn", f"{config.llm.model}  listed · images: no → "
                                           "Explain screen needs a vision model"))
    return rows


def check_hotkey(env, combo: str) -> Check:
    if env.get("XDG_SESSION_TYPE") == "wayland":
        return Check("Hotkey", "fail", "Wayland can't grab global keys → bind a desktop "
                                       "shortcut to `kami toggle`")
    try:
        import pynput  # noqa: F401
    except ImportError:
        return Check("Hotkey", "fail", "pynput not installed → pip install 'kami[hotkey]' "
                                       "or bind a desktop shortcut to `kami toggle`")
    except Exception as exc:  # pynput can fail on import without an X display
        return Check("Hotkey", "fail", f"pynput can't start ({type(exc).__name__}) → "
                                       "bind a desktop shortcut to `kami toggle`")
    return Check("Hotkey", "ok", f"{combo} via pynput")


def check_screen_grab(env) -> Check:
    session = env.get("XDG_SESSION_TYPE")
    if session == "wayland":
        return Check("Screen grab", "warn", "Wayland: Explain screen may capture a blank image "
                                            "(portal support is Phase 3)")
    if session == "x11":
        return Check("Screen grab", "ok", "X11")
    return Check("Screen grab", "warn", "unknown session; capture may not work")


def check_running() -> Check:
    try:
        from PySide6.QtNetwork import QLocalSocket

        from kami.app import SOCKET_NAME
    except Exception:  # Qt can't load here (e.g. missing system libraries)
        return Check("Running", "info", "skipped (Qt unavailable)")
    socket = QLocalSocket()
    socket.connectToServer(SOCKET_NAME)
    if socket.waitForConnected(300):
        socket.disconnectFromServer()  # connect only: sending "toggle" would pop the panel
        return Check("Running", "ok", "an instance is answering on the local socket")
    return Check("Running", "info", "not running (start it with: kami)")


def collect(env=None, config_path: Path | None = None,
            http: httpx.Client | None = None, running: bool = True) -> list[Check]:
    env = os.environ if env is None else env
    checks: list[Check] = []

    def guarded(fn, *args):
        try:
            result = fn(*args)
        except Exception as exc:  # one broken check must not stop the report
            result = Check(fn.__name__.removeprefix("check_").replace("_", " ").capitalize(),
                           "fail", f"check crashed ({type(exc).__name__})")
        return result if isinstance(result, list) else [result]

    checks += guarded(check_session, env)
    try:
        rows, config = check_config(config_path or CONFIG_PATH)
    except Exception as exc:
        rows, config = [Check("Config", "fail", f"check crashed ({type(exc).__name__})")], None
    checks += rows
    config = config or Config()  # keep going with defaults so the other rows still render
    checks += guarded(check_api_key, env, config)
    checks += guarded(check_endpoint_and_model, config, http)
    checks += guarded(check_hotkey, env, config.hotkey)
    checks += guarded(check_screen_grab, env)
    if running:
        checks += guarded(check_running)
    checks.append(Check("Log file", "info", str(default_state_dir() / "kami.log")
                        .replace(str(Path.home()), "~", 1)))
    return checks


def render(checks: list[Check]) -> str:
    lines = [f"Kami {__version__} · Python {platform.python_version()}"]
    for check in checks:
        lines.append(f"{check.name:<13} {SYMBOLS[check.status]} {check.detail}")
    return "\n".join(lines)


def exit_code(checks: list[Check]) -> int:
    return 1 if any(c.status == "fail" for c in checks) else 0


def run_doctor() -> int:
    checks = collect()
    print(render(checks))
    return exit_code(checks)
