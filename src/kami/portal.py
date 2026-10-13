"""The desktop's Screenshot portal, minus the D-Bus: tokens, reply parsing, the file.
No Qt, so pytest covers it. `ui/portal.py` makes the D-Bus call and hands the reply here.

On Wayland, Explain screen asks `org.freedesktop.portal.Screenshot` for a full-screen
shot. The portal answers later with a `Response(u code, a{sv} results)` signal on a
request object, and (on GNOME 46) writes a PNG into `~/Pictures/` whose `file://` URI is
in `results["uri"]`.

Privacy rules:

- `load_screenshot` is the only Kami code that opens the portal's file. It accepts only a
  `file://` URI with an empty or `localhost` host and an absolute path, and only a
  regular file (`lstat` first, then `O_RDONLY | O_NOFOLLOW | O_NONBLOCK` and `fstat`
  again). It reads at most `max_bytes + 1` bytes (64 MB by default).
- Once the URI and `lstat` checks pass, it deletes that exact path whether or not the
  read worked. It never deletes anything that failed those checks.
- Its errors never contain the path and carry no chained `OSError`
  (`__cause__` and `__context__` are both None).
- The URI and the image bytes are left out of the dataclass `repr`s. Nothing here logs.
- The full-screen image lives in the panel's memory only until the crop or the cancel;
  only the crop is ever sent, and only after you ask.
"""
from __future__ import annotations

import os
import secrets
import stat
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

HIDE_DELAY_MS = 150            # wait after hiding the panel (Task 1, Q10: enough on GNOME 46)
SCREENSHOT_TIMEOUT_MS = 60_000
MAX_SCREENSHOT_BYTES = 64 * 1024 * 1024
CROP_FAILED = "Kami couldn't line the screenshot up with your screens."
READ_FAILED = "Kami couldn't read the screenshot"   # the panel adds ": <reason>" or "."
NOT_DELETED = "Kami couldn't delete the desktop's temporary screenshot file."

CANCELLED_MESSAGE = (
    "Screenshot cancelled. Kami needs permission to see your screen for Explain screen. "
    "Click Explain screen to try again."
)
FAILED_MESSAGE = "The desktop couldn't take the screenshot. Run `kami doctor` to see why."
TIMEOUT_MESSAGE = (
    "The desktop's screenshot service didn't answer within 60 seconds. "
    "Click Explain screen to try again."
)

_REQUEST_ROOT = "/org/freedesktop/portal/desktop/request"
_UINT32_MAX = 2**32 - 1        # D-Bus `u`: anything else isn't a real response code
_CHUNK = 1024 * 1024

_NOT_LOCAL = "the screenshot address isn't a local file"
_NOT_REGULAR = "the screenshot isn't a regular file"
_CANT_READ = "couldn't read the screenshot file"
_TOO_BIG = "the screenshot file is too big"


@dataclass(frozen=True)
class ScreenshotReply:
    status: str                               # "ok" | "cancelled" | "failed" | "timeout"
    uri: str = field(default="", repr=False)  # only when status == "ok"; never logged
    reason: str = ""                          # short, safe to log, e.g. "response=2"


@dataclass(frozen=True)
class LoadedShot:
    png: bytes = field(repr=False)  # the file's bytes as the portal wrote them (PNG)
    deleted: bool                   # False if the file could not be removed


class ScreenshotFileError(Exception):
    """Plain-words reason; never contains the path; raised with no chained exception."""


def new_token() -> str:
    """A fresh `handle_token`: `kami_` + 16 hex chars, valid in a D-Bus object path."""
    return "kami_" + secrets.token_hex(8)


def request_path(unique_name: str, token: str) -> str:
    """The Request object the portal will use, so we can subscribe before calling.
    `":1.42", "kami_ab"` -> `/org/freedesktop/portal/desktop/request/1_42/kami_ab`."""
    sender = unique_name.removeprefix(":").replace(".", "_")
    return f"{_REQUEST_ROOT}/{sender}/{token}"


def parse_screenshot_reply(code: object, results: Mapping[str, object]) -> ScreenshotReply:
    """Turn a `Response` into a reply. Both arguments came over D-Bus: untrusted."""
    if isinstance(code, bool) or not isinstance(code, int) or not 0 <= code <= _UINT32_MAX:
        return ScreenshotReply("failed", reason="bad response")
    if code == 1:
        return ScreenshotReply("cancelled")
    if code != 0:
        return ScreenshotReply("failed", reason=f"response={code}")
    uri = results.get("uri") if isinstance(results, Mapping) else None
    if not isinstance(uri, str):
        return ScreenshotReply("failed", reason="no uri")
    if not uri.startswith("file://"):
        return ScreenshotReply("failed", reason="not a file uri")
    return ScreenshotReply("ok", uri=uri)


def timed_out() -> ScreenshotReply:
    return ScreenshotReply("timeout", reason="timeout")


def reply_message(reply: ScreenshotReply) -> str:
    """Panel text for a reply that isn't `ok`. Never includes the URI."""
    if reply.status == "cancelled":
        return CANCELLED_MESSAGE
    if reply.status == "timeout":
        return TIMEOUT_MESSAGE
    return FAILED_MESSAGE


def load_screenshot(uri: str, max_bytes: int = MAX_SCREENSHOT_BYTES) -> LoadedShot:
    """Read the portal's file into memory and delete it. Runs on the worker thread.
    Raises ScreenshotFileError (see the module docstring for the rules)."""
    path = _local_path(uri)
    if path is None:
        raise ScreenshotFileError(_NOT_LOCAL)

    problem = ""
    try:
        is_regular = stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        problem = _CANT_READ
    if problem:
        raise ScreenshotFileError(problem)
    if not is_regular:
        raise ScreenshotFileError(_NOT_REGULAR)

    try:
        data, problem = _read_regular(path, max_bytes)
    finally:
        deleted = _delete(path)
    if problem:
        raise ScreenshotFileError(problem)
    return LoadedShot(data, deleted)


def _local_path(uri: object) -> str | None:
    """The absolute local path in a `file://` URI, or None if it isn't one."""
    if not isinstance(uri, str):
        return None
    try:
        parts = urlsplit(uri)
    except ValueError:          # e.g. a broken `[` IPv6 host
        return None
    if parts.scheme != "file" or parts.netloc not in ("", "localhost"):
        return None
    if parts.query or parts.fragment:
        return None
    path = unquote(parts.path)
    if "\0" in path or not os.path.isabs(path):
        return None
    return path


def _read_regular(path: str, max_bytes: int) -> tuple[bytes, str]:
    """(data, "") or (b"", problem). Never raises OSError and never names the path."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return b"", _CANT_READ
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            return b"", _NOT_REGULAR
        if info.st_size > max_bytes:
            return b"", _TOO_BIG
        chunks: list[bytes] = []
        total = 0
        while total <= max_bytes:   # stops at max_bytes + 1 even if the file grows
            chunk = os.read(fd, min(_CHUNK, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        if total > max_bytes:
            return b"", _TOO_BIG
        return b"".join(chunks), ""
    except OSError:
        return b"", _CANT_READ
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _delete(path: str) -> bool:
    """Remove the portal's file. Already gone counts as deleted."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True
