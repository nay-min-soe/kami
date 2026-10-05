"""App-control mode: hands-free actions inside allowed apps.

Every action goes through `kami.safety.gate` first. Handlers are registered
per action kind; only "launch" exists so far.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable

from kami.config import AppControlConfig
from kami.safety import ConfirmFn, NotAllowed, ProposedAction, gate

Handler = Callable[[ProposedAction], str]

log = logging.getLogger(__name__)


def _launch(action: ProposedAction) -> str:
    exe = shutil.which(action.app)
    if not exe:
        return f"Could not find '{action.app}' on PATH."
    subprocess.Popen([exe], start_new_session=True)
    return f"Opened {action.app}."


HANDLERS: dict[str, Handler] = {"launch": _launch}


def run(kind: str, action: ProposedAction, policy: AppControlConfig, confirm: ConfirmFn) -> str:
    # %r: names may come from the model, so quote them to keep one event per log line.
    handler = HANDLERS.get(kind)
    if handler is None:
        log.info("app_control kind=%r app=%r outcome=unknown_kind", kind, action.app)
        return f"Kami doesn't know how to '{kind}' yet."
    try:
        allowed = gate(action, policy, confirm)
    except NotAllowed:
        log.info("app_control kind=%r app=%r outcome=refused_not_allowed", kind, action.app)
        raise
    if not allowed:
        log.info("app_control kind=%r app=%r outcome=cancelled", kind, action.app)
        return "Cancelled. Nothing was changed."
    outcome = "confirmed" if action.sensitive else "allowed"
    log.info("app_control kind=%r app=%r outcome=%s", kind, action.app, outcome)
    return handler(action)
