import os
import re
import stat
import traceback
from pathlib import Path

import pytest

from kami import portal
from kami.portal import (
    LoadedShot,
    ScreenshotFileError,
    ScreenshotReply,
    load_screenshot,
    new_token,
    parse_screenshot_reply,
    reply_message,
    request_path,
    timed_out,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"fake image body" * 10


def _uri(path: Path) -> str:
    return path.as_uri()


def _shot(tmp_path: Path, name: str = "Screenshot.png", data: bytes = PNG) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _refusal(uri: str, **kwargs) -> ScreenshotFileError:
    with pytest.raises(ScreenshotFileError) as info:
        load_screenshot(uri, **kwargs)
    return info.value


# --- tokens and request paths -------------------------------------------------------

def test_request_path_from_unique_name():
    assert (request_path(":1.42", "kami_ab")
            == "/org/freedesktop/portal/desktop/request/1_42/kami_ab")
    assert (request_path(":1.257", "kami_x")
            == "/org/freedesktop/portal/desktop/request/1_257/kami_x")


def test_new_token_is_unique_and_safe():
    tokens = {new_token() for _ in range(200)}
    assert len(tokens) == 200
    for token in tokens:
        assert re.fullmatch(r"kami_[0-9a-f]{16}", token)
        assert re.fullmatch(r"[A-Za-z0-9_]+", token)   # valid in a D-Bus object path


# --- parse_screenshot_reply ---------------------------------------------------------

def test_reply_ok_file_uri():
    reply = parse_screenshot_reply(0, {"uri": "file:///home/me/Pictures/Screenshot.png"})
    assert reply.status == "ok"
    assert reply.uri == "file:///home/me/Pictures/Screenshot.png"
    assert reply.reason == ""


def test_reply_cancelled():
    reply = parse_screenshot_reply(1, {"uri": "file:///x.png"})
    assert reply.status == "cancelled"
    assert reply.uri == ""


@pytest.mark.parametrize("code", [2, 3, 7])
def test_reply_error_code(code):
    reply = parse_screenshot_reply(code, {"uri": "file:///x.png"})
    assert (reply.status, reply.reason, reply.uri) == ("failed", f"response={code}", "")


@pytest.mark.parametrize("results", [{}, {"uri": None}, {"uri": b"file:///x.png"},
                                     {"uri": ["file:///x.png"]}, None, "file:///x.png"])
def test_reply_missing_uri(results):
    reply = parse_screenshot_reply(0, results)
    assert (reply.status, reply.reason, reply.uri) == ("failed", "no uri", "")


@pytest.mark.parametrize("uri", ["http://evil.example/x.png", "/home/me/x.png",
                                 "FILE:///x.png", "smb://host/x.png", ""])
def test_reply_rejects_non_file_uri(uri):
    reply = parse_screenshot_reply(0, {"uri": uri})
    assert (reply.status, reply.reason, reply.uri) == ("failed", "not a file uri", "")


@pytest.mark.parametrize("code", ["0", None, 0.0, True, False, [0], 2**32, -1])
def test_reply_bad_code_type(code):
    reply = parse_screenshot_reply(code, {"uri": "file:///x.png"})
    assert (reply.status, reply.reason, reply.uri) == ("failed", "bad response", "")


def test_reply_huge_int_does_not_crash():
    # str() of a giant int raises ValueError in Python 3.11+; it must never get that far.
    assert parse_screenshot_reply(10**5000, {}).reason == "bad response"


def test_reply_repr_hides_uri():
    reply = parse_screenshot_reply(0, {"uri": "file:///home/me/Pictures/secret.png"})
    assert "file://" not in repr(reply)
    assert "secret" not in repr(reply)
    assert "ok" in repr(reply)


def test_timed_out():
    assert timed_out() == ScreenshotReply("timeout", reason="timeout")


@pytest.mark.parametrize("reply", [
    ScreenshotReply("cancelled"),
    ScreenshotReply("failed", reason="response=2"),
    ScreenshotReply("timeout", reason="timeout"),
    ScreenshotReply("ok", uri="file:///home/me/Pictures/secret.png"),
    ScreenshotReply("failed", uri="file:///home/me/Pictures/secret.png", reason="dbus error"),
])
def test_reply_message_never_contains_uri(reply):
    message = reply_message(reply)
    assert message
    assert "file://" not in message
    assert "secret" not in message


def test_reply_message_texts():
    assert reply_message(ScreenshotReply("cancelled")).startswith("Screenshot cancelled.")
    assert "kami doctor" in reply_message(ScreenshotReply("failed", reason="response=2"))
    assert "60 seconds" in reply_message(timed_out())


# --- load_screenshot ----------------------------------------------------------------

def test_load_reads_and_deletes(tmp_path):
    path = _shot(tmp_path)
    shot = load_screenshot(_uri(path))
    assert shot == LoadedShot(PNG, True)
    assert not path.exists()


def test_loaded_shot_repr_hides_png():
    assert "PNG" not in repr(LoadedShot(PNG, True))


def test_load_accepts_localhost_host(tmp_path):
    path = _shot(tmp_path)
    assert load_screenshot(f"file://localhost{path}").png == PNG
    assert not path.exists()


def test_load_percent_encoded_path(tmp_path):
    path = _shot(tmp_path, "a b.png")
    uri = _uri(path)
    assert "%20" in uri
    assert load_screenshot(uri).png == PNG
    assert not path.exists()


def test_load_rejects_other_schemes(tmp_path):
    path = _shot(tmp_path)
    for uri in (f"http://localhost{path}", str(path), f"file://otherhost{path}",
                f"file://localhost:80{path}", f"file://user@localhost{path}",
                f"file://{path}?x=1", f"file://{path}#frag"):
        error = _refusal(uri)
        assert str(error) == "the screenshot address isn't a local file", uri
        assert path.read_bytes() == PNG    # untouched


def test_load_rejects_relative_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = _shot(tmp_path, "rel.png")
    for uri in ("file:rel.png", "file://rel.png"):
        assert str(_refusal(uri)) == "the screenshot address isn't a local file"
    assert path.read_bytes() == PNG


@pytest.mark.parametrize("uri", [None, b"file:///x.png", 42, "file:///tmp/a%00b.png",
                                 "file://[::1/x.png"])
def test_load_rejects_malformed_uri(uri):
    error = _refusal(uri)
    assert str(error) == "the screenshot address isn't a local file"
    assert error.__context__ is None and error.__cause__ is None


def test_load_refuses_symlink_and_keeps_target(tmp_path):
    target = _shot(tmp_path, "precious.txt", b"do not delete me")
    link = tmp_path / "Screenshot.png"
    link.symlink_to(target)
    assert str(_refusal(_uri(link))) == "the screenshot isn't a regular file"
    assert target.read_bytes() == b"do not delete me"
    assert link.is_symlink()       # nothing that failed the checks is deleted


def test_load_refuses_directory(tmp_path):
    folder = tmp_path / "Screenshot.png"
    folder.mkdir()
    assert str(_refusal(_uri(folder))) == "the screenshot isn't a regular file"
    assert folder.is_dir()


def test_load_refuses_fifo_without_blocking(tmp_path):
    fifo = tmp_path / "Screenshot.png"
    os.mkfifo(fifo)
    # No writer: a blocking open or read would hang here, and pytest would never finish.
    assert str(_refusal(_uri(fifo))) == "the screenshot isn't a regular file"
    assert stat.S_ISFIFO(os.lstat(fifo).st_mode)    # left in place


def _lstat_says_regular(monkeypatch, regular: Path) -> None:
    """Simulate a file swapped between the lstat check and the open."""
    real = os.stat(regular)
    monkeypatch.setattr(os, "lstat", lambda _path: real)


def test_load_fifo_swapped_in_after_lstat_is_refused_by_fstat(tmp_path, monkeypatch):
    fifo = tmp_path / "Screenshot.png"
    os.mkfifo(fifo)
    _lstat_says_regular(monkeypatch, _shot(tmp_path, "other.png"))
    # O_NONBLOCK: the open returns at once, then fstat sees a FIFO.
    assert str(_refusal(_uri(fifo))) == "the screenshot isn't a regular file"
    assert not fifo.exists()       # past the lstat check, so the path is removed


def test_load_symlink_swapped_in_after_lstat_keeps_target(tmp_path, monkeypatch):
    target = _shot(tmp_path, "precious.txt", b"do not delete me")
    link = tmp_path / "Screenshot.png"
    link.symlink_to(target)
    _lstat_says_regular(monkeypatch, target)
    error = _refusal(_uri(link))
    assert str(error) == "couldn't read the screenshot file"    # O_NOFOLLOW refused it
    assert target.read_bytes() == b"do not delete me"           # only the link went
    assert not link.is_symlink()


def test_load_too_big_is_deleted_and_refused(tmp_path):
    path = _shot(tmp_path, data=b"x" * 11)
    assert str(_refusal(_uri(path), max_bytes=10)) == "the screenshot file is too big"
    assert not path.exists()


def test_load_exactly_max_bytes_is_fine(tmp_path):
    path = _shot(tmp_path, data=b"x" * 10)
    assert load_screenshot(_uri(path), max_bytes=10) == LoadedShot(b"x" * 10, True)


def test_load_reads_in_chunks(tmp_path):
    data = os.urandom(3 * 1024 * 1024 + 7)
    path = _shot(tmp_path, data=data)
    assert load_screenshot(_uri(path)).png == data


def test_load_growing_file_is_capped(tmp_path, monkeypatch):
    # fstat said small, but more bytes arrive: the read still stops at max_bytes + 1.
    path = _shot(tmp_path, data=b"x" * 50)
    real_fstat = os.fstat

    def small_fstat(fd):
        st = real_fstat(fd)
        return os.stat_result((st.st_mode, st.st_ino, st.st_dev, st.st_nlink, st.st_uid,
                               st.st_gid, 5, st.st_atime, st.st_mtime, st.st_ctime))

    monkeypatch.setattr(os, "fstat", small_fstat)
    assert str(_refusal(_uri(path), max_bytes=10)) == "the screenshot file is too big"
    assert not path.exists()


def test_load_missing_file_error_has_no_path(tmp_path):
    path = tmp_path / "secret-name-2026.png"
    error = _refusal(_uri(path))
    assert str(error) == "couldn't read the screenshot file"
    assert error.__cause__ is None
    assert error.__context__ is None
    text = "".join(traceback.format_exception(error))
    assert "secret-name" not in text
    assert str(tmp_path) not in text


def test_load_read_error_has_no_path_and_still_deletes(tmp_path, monkeypatch):
    path = _shot(tmp_path, "secret-name.png")

    def broken_read(_fd, _n):
        raise OSError(5, "Input/output error", str(path))

    monkeypatch.setattr(os, "read", broken_read)
    error = _refusal(_uri(path))
    assert str(error) == "couldn't read the screenshot file"
    assert error.__cause__ is None and error.__context__ is None
    assert "secret-name" not in "".join(traceback.format_exception(error))
    assert not path.exists()


def test_load_delete_failure_is_reported(tmp_path, monkeypatch):
    path = _shot(tmp_path)

    def refuse(_path):
        raise PermissionError(13, "Permission denied", str(_path))

    monkeypatch.setattr(os, "unlink", refuse)
    assert load_screenshot(_uri(path)) == LoadedShot(PNG, False)


def test_load_already_gone_counts_as_deleted(tmp_path, monkeypatch):
    path = _shot(tmp_path)
    real_unlink = os.unlink

    def gone(p):
        real_unlink(p)
        raise FileNotFoundError(2, "No such file or directory", str(p))

    monkeypatch.setattr(os, "unlink", gone)
    assert load_screenshot(_uri(path)).deleted is True


def test_messages_are_plain_constants():
    assert portal.CROP_FAILED.endswith(".")
    assert portal.NOT_DELETED.endswith(".")
    assert not portal.READ_FAILED.endswith((".", ":"))   # the panel adds ": reason" or "."
    assert portal.HIDE_DELAY_MS == 150
    assert portal.SCREENSHOT_TIMEOUT_MS == 60_000
    assert portal.MAX_SCREENSHOT_BYTES == 64 * 1024 * 1024
