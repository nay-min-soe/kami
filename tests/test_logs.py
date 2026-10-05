import logging

import httpx
import pytest

from kami import logs
from kami.config import AppControlConfig, LLMConfig
from kami.llm import LLMClient, LLMError
from kami.modes import app_control
from kami.safety import ProposedAction


@pytest.fixture
def log_file(tmp_path):
    """Set up logging in a temp dir, then remove the handlers so tests don't leak."""
    path = logs.setup_logging(tmp_path / "state")
    yield path
    logger = logging.getLogger("kami")
    for handler in [h for h in logger.handlers if getattr(h, "kami", False)]:
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(logging.NOTSET)


def written(path) -> str:
    for handler in logging.getLogger("kami").handlers:
        handler.flush()
    return path.read_text()


def test_creates_log_file_in_state_dir(log_file, tmp_path):
    logging.getLogger("kami.test").info("hello log")
    assert log_file.parent == tmp_path / "state"
    assert "hello log" in written(log_file)


def test_log_dir_is_private(log_file):
    assert log_file.parent.stat().st_mode & 0o777 == 0o700


def test_redacts_key_patterns(log_file):
    logging.getLogger("kami.test").info("key %s", "sk-or-abc123def456ghi")
    text = written(log_file)
    assert "[redacted]" in text
    assert "abc123def456ghi" not in text


def test_redacts_configured_key():
    record = logging.LogRecord("kami", logging.INFO, __file__, 1, "using %s", ("plainkey987",),
                               None)
    logs.RedactKeys({"plainkey987"}).filter(record)
    assert record.getMessage() == "using [redacted]"


def test_redacts_key_inside_traceback(log_file):
    try:
        raise RuntimeError("bad key sk-or-zzz111yyy222")
    except RuntimeError:
        logging.getLogger("kami.test").exception("boom")
    text = written(log_file)
    assert "RuntimeError" in text
    assert "zzz111yyy222" not in text


def test_llm_error_logs_kind_not_body(caplog):
    def handler(_request):
        return httpx.Response(401, json={"error": {"code": 401, "message": "nope"}})

    cfg = LLMConfig(base_url="https://llm.example/v1", model="x/y", api_key="sk-test-0123456789")
    client = LLMClient(cfg, http=httpx.Client(transport=httpx.MockTransport(handler)))
    caplog.set_level(logging.INFO, logger="kami")
    with pytest.raises(LLMError):
        client.ask("my secret question")
    assert "kind=auth" in caplog.text
    assert "my secret question" not in caplog.text
    assert "0123456789" not in caplog.text


def test_app_control_logs_refusal(caplog):
    caplog.set_level(logging.INFO, logger="kami")
    action = ProposedAction(app="firefox", description="open Firefox", risks=["A window opens"])
    app_control.run("launch", action, AppControlConfig(allowed_apps=["firefox"]),
                    confirm=lambda a: False)
    assert "outcome=cancelled" in caplog.text
    assert "'firefox'" in caplog.text and "'launch'" in caplog.text
