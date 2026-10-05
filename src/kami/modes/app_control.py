"""App-control mode: hands-free actions inside allowed apps.

Every action goes through `kami.safety.gate` first. Handlers are registered
per action kind; only "launch" exists so far.
"""
from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable

from kami.config import AppControlConfig
from kami.safety import ConfirmFn, ProposedAction, gate

Handler = Callable[[ProposedAction], str]


def _launch(action: ProposedAction) -> str:
    exe = shutil.which(action.app)
    if not exe:
        return f"Could not find '{action.app}' on PATH."
    subprocess.Popen([exe], start_new_session=True)
    return f"Opened {action.app}."


HANDLERS: dict[str, Handler] = {"launch": _launch}


def run(kind: str, action: ProposedAction, policy: AppControlConfig, confirm: ConfirmFn) -> str:
    handler = HANDLERS.get(kind)
    if handler is None:
        return f"Kami doesn't know how to '{kind}' yet."
    if not gate(action, policy, confirm):
        return "Cancelled. Nothing was changed."
    return handler(action)
