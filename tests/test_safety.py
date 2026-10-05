import pytest

from kami.config import AppControlConfig
from kami.safety import NotAllowed, ProposedAction, gate

POLICY = AppControlConfig(allowed_apps=["firefox"])


def test_blocks_apps_outside_allowlist():
    action = ProposedAction(app="terminal", description="run a command")
    with pytest.raises(NotAllowed):
        gate(action, POLICY, confirm=lambda a: True)


def test_sensitive_action_needs_yes():
    action = ProposedAction(app="firefox", description="close all tabs", risks=["Tabs lost"])
    assert gate(action, POLICY, confirm=lambda a: True) is True
    assert gate(action, POLICY, confirm=lambda a: False) is False


def test_confirm_always_sees_a_risk_explanation():
    seen = []
    action = ProposedAction(app="firefox", description="submit the form")
    gate(action, POLICY, confirm=lambda a: seen.append(list(a.risks)) or False)
    assert seen and seen[0], "user must be shown possible outcomes"


def test_non_sensitive_action_skips_dialog():
    def never(_a):
        raise AssertionError("should not ask")
    action = ProposedAction(app="firefox", description="open", sensitive=False)
    assert gate(action, POLICY, confirm=never) is True


def test_ci_turns_red():
    assert False, "throwaway: proves CI fails on a broken test"
