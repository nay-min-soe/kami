import pytest

from kami.config import AppControlConfig
from kami.modes import app_control
from kami.safety import NotAllowed, ProposedAction

POLICY = AppControlConfig(allowed_apps=["firefox"])


@pytest.fixture
def popen_calls(monkeypatch) -> list[tuple]:
    """Replace Popen and which so no test can start a real process."""
    calls: list[tuple] = []
    monkeypatch.setattr(app_control.subprocess, "Popen",
                        lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(app_control.shutil, "which", lambda name: f"/usr/bin/{name}")
    return calls


def never_ask(_action):
    raise AssertionError("confirm should not be called")


def firefox() -> ProposedAction:
    return ProposedAction(app="firefox", description="open Firefox", risks=["A window opens"])


def test_unknown_kind_returns_message_and_never_asks(popen_calls):
    result = app_control.run("delete", firefox(), POLICY, confirm=never_ask)
    assert "doesn't know how" in result
    assert popen_calls == []


def test_not_allowed_app_raises_and_never_launches(popen_calls):
    action = ProposedAction(app="terminal", description="open a terminal")
    with pytest.raises(NotAllowed):
        app_control.run("launch", action, POLICY, confirm=lambda a: True)
    assert popen_calls == []


def test_refused_confirm_launches_nothing(popen_calls):
    result = app_control.run("launch", firefox(), POLICY, confirm=lambda a: False)
    assert result.startswith("Cancelled")
    assert popen_calls == []


def test_confirmed_launch_runs_resolved_path(popen_calls):
    result = app_control.run("launch", firefox(), POLICY, confirm=lambda a: True)
    assert result == "Opened firefox."
    assert popen_calls == [((["/usr/bin/firefox"],), {"start_new_session": True})]


def test_launch_missing_binary(popen_calls, monkeypatch):
    monkeypatch.setattr(app_control.shutil, "which", lambda name: None)
    result = app_control.run("launch", firefox(), POLICY, confirm=lambda a: True)
    assert "Could not find" in result
    assert popen_calls == []


def test_launch_passes_no_shell(popen_calls):
    app_control.run("launch", firefox(), POLICY, confirm=lambda a: True)
    (_args, kwargs), = popen_calls
    assert "shell" not in kwargs, "app names must never reach a shell"


def test_every_handler_kind_goes_through_gate(popen_calls, monkeypatch):
    ran: list[str] = []
    for kind in app_control.HANDLERS:
        monkeypatch.setitem(app_control.HANDLERS, kind, lambda a, k=kind: ran.append(k) or "")
    for kind in app_control.HANDLERS:
        app_control.run(kind, firefox(), POLICY, confirm=lambda a: False)
    assert ran == [], "a handler ran without the user saying yes"
