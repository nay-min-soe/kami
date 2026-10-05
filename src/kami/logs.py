"""File logging: ~/.local/state/kami/kami.log, rotated at 1 MB (3 old files kept).

What we log: start-up facts, which task ran, model name, durations, error kinds and
app-control decisions. What we never log: API keys, screenshots, prompts, model
replies or transcripts. As a backstop, RedactKeys scrubs anything key-shaped.
Named logs.py, not logging.py, so it doesn't shadow the standard library.
"""
from __future__ import annotations

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{10,}")
REDACTED = "[redacted]"

_redactor: RedactKeys | None = None


def default_state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(base) / "kami"


class RedactKeys(logging.Filter):
    """Replaces key-shaped text, and any secret it was given, in messages and tracebacks."""

    def __init__(self, secrets: set[str] | None = None) -> None:
        super().__init__()
        self.secrets = {s for s in (secrets or set()) if s}

    def redact(self, text: str) -> str:
        text = KEY_PATTERN.sub(REDACTED, text)
        for secret in self.secrets:
            text = text.replace(secret, REDACTED)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        record.msg, record.args = self.redact(message), None
        if record.exc_info and not record.exc_text:
            record.exc_text = self.redact(logging.Formatter().formatException(record.exc_info))
        return True


def remember_secret(value: str) -> None:
    """Also redact this exact value (e.g. a configured key without the sk- prefix)."""
    if _redactor and value:
        _redactor.secrets.add(value)


def setup_logging(state_dir: Path | None = None) -> Path:
    """Attach the file and stderr handlers to the `kami` logger. Returns the log path."""
    global _redactor
    directory = Path(state_dir) if state_dir else default_state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    path = directory / "kami.log"

    logger = logging.getLogger("kami")
    for old in [h for h in logger.handlers if getattr(h, "kami", False)]:
        logger.removeHandler(old)
        old.close()
    level = os.environ.get("KAMI_LOG_LEVEL", "INFO").upper()
    logger.setLevel(level if level in logging.getLevelNamesMapping() else "INFO")

    _redactor = RedactKeys()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    to_file = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    to_stderr = logging.StreamHandler()
    to_stderr.setLevel(logging.WARNING)
    for handler in (to_file, to_stderr):
        handler.kami = True
        handler.setFormatter(formatter)
        handler.addFilter(_redactor)  # handler-level, so it also covers child loggers
        logger.addHandler(handler)

    # At INFO, httpx logs every request URL. Keep it and its transport quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    return path
