import httpx
import pytest

from kami import doctor
from kami.cli import main

MODELS = {"data": [
    {"id": "openrouter/auto", "architecture": {"input_modalities": ["text", "image"]}},
    {"id": "text/only", "architecture": {"input_modalities": ["text"]}},
]}


def models_http(body=None, fail_on_chat: bool = True):
    def handler(request):
        if request.url.path.endswith("/chat/completions") and fail_on_chat:
            raise AssertionError("doctor must never send a chat request (it costs money)")
        return httpx.Response(200, json=MODELS if body is None else body)
    return httpx.Client(transport=httpx.MockTransport(handler))


def report(tmp_path, env, toml: str = "", http=None) -> list[doctor.Check]:
    path = tmp_path / "config.toml"
    if toml:
        path.write_text(toml)
    return doctor.collect(env=env, config_path=path, http=http or models_http(), running=False)


def row(checks, name) -> doctor.Check:
    return next(c for c in checks if c.name == name)


def test_session_check_wayland_hotkey_fails(tmp_path):
    checks = report(tmp_path, {"XDG_SESSION_TYPE": "wayland"})
    hotkey = row(checks, "Hotkey")
    assert hotkey.status == "fail" and "kami toggle" in hotkey.detail
    assert row(checks, "Screen grab").status == "warn"


def test_session_check_x11_without_pynput(tmp_path, monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "pynput", None)  # makes the import fail
    hotkey = row(report(tmp_path, {"XDG_SESSION_TYPE": "x11"}), "Hotkey")
    assert hotkey.status == "fail" and "pip install" in hotkey.detail


def test_api_key_source_reported_not_value(tmp_path):
    checks = report(tmp_path, {"OPENROUTER_API_KEY": "sk-secret123"})
    text = doctor.render(checks)
    assert "OPENROUTER_API_KEY" in text
    assert "secret123" not in text


def test_config_error_is_a_failed_check_not_a_crash(tmp_path):
    checks = report(tmp_path, {}, toml="[llm\n")
    assert row(checks, "Config").status == "fail"
    assert row(checks, "Endpoint").status == "ok"  # the rest of the report still ran


def test_config_warnings_listed(tmp_path):
    checks = report(tmp_path, {}, toml="[app_control]\nallowed_app = []\n")
    assert any(c.status == "warn" and "allowed_apps" in c.detail for c in checks)


def test_endpoint_unreachable_is_failure(tmp_path):
    def handler(request):
        raise httpx.ConnectError("down", request=request)
    checks = report(tmp_path, {}, http=httpx.Client(transport=httpx.MockTransport(handler)))
    endpoint = row(checks, "Endpoint")
    assert endpoint.status == "fail" and "Can't reach" in endpoint.detail


def test_model_not_listed_warns(tmp_path):
    checks = report(tmp_path, {}, toml='[llm]\nmodel = "nope/missing"\n')
    assert row(checks, "Model").status == "warn"


def test_text_only_model_warns_about_images(tmp_path):
    checks = report(tmp_path, {}, toml='[llm]\nmodel = "text/only"\n')
    model = row(checks, "Model")
    assert model.status == "warn" and "images: no" in model.detail


def test_doctor_never_posts_chat(tmp_path):
    # models_http raises if /chat/completions is requested; a full report must not.
    report(tmp_path, {"OPENROUTER_API_KEY": "sk-test-0123456789"})


def test_exit_code_reflects_failures():
    ok = [doctor.Check("A", "ok", ""), doctor.Check("B", "warn", ""), doctor.Check("C", "info", "")]
    assert doctor.exit_code(ok) == 0
    assert doctor.exit_code(ok + [doctor.Check("D", "fail", "")]) == 1


def test_cli_doctor_command_runs_report(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "collect", lambda: [doctor.Check("Session", "ok", "x11")])
    assert main(["doctor"]) == 0
    assert "Session" in capsys.readouterr().out


@pytest.mark.parametrize("status", sorted(doctor.SYMBOLS))
def test_every_status_renders(status):
    assert doctor.SYMBOLS[status] in doctor.render([doctor.Check("X", status, "d")])
