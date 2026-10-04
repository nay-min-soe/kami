"""The permission gate every app-control action must pass.

Rules (from the Kami design):
  1. Kami only acts inside apps the user listed in `allowed_apps`.
  2. Sensitive actions need explicit confirmation, and the prompt must explain
     what the action does and what could go wrong.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from kami.config import AppControlConfig


@dataclass
class ProposedAction:
    app: str
    description: str                      # e.g. "Delete 3 files from ~/Downloads"
    risks: list[str] = field(default_factory=list)  # e.g. ["Files cannot be recovered"]
    sensitive: bool = True                # default to the safe assumption


class NotAllowed(Exception):
    """Raised when an action targets an app the user has not allowed."""


ConfirmFn = Callable[[ProposedAction], bool]


def gate(action: ProposedAction, policy: AppControlConfig, confirm: ConfirmFn) -> bool:
    """Return True only if the action may run.

    Raises NotAllowed for apps outside the allowlist. For sensitive actions the
    `confirm` callback (a dialog in the UI, a stub in tests) must return True.
    """
    if not policy.is_allowed(action.app):
        raise NotAllowed(f"Kami is not allowed to control '{action.app}'.")
    if action.sensitive:
        if not action.risks:
            # Never ask for a blind yes: the user must see possible outcomes.
            action.risks = ["Kami could not predict the outcome. Check before allowing."]
        return bool(confirm(action))
    return True
