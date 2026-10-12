"""Phase 3 spike, Q8 on KDE: bind Kami's hotkey through the GlobalShortcuts portal.

CreateSession -> BindShortcuts ("toggle", preferred CTRL+ALT+k) -> prints Activated for
30 s -> closes the session. ``--register`` first calls
``org.freedesktop.host.portal.Registry.Register("org.kami.Kami", {})`` (if that
interface exists), to compare how the desktop names the app.

QtDBus can't send ``BindShortcuts``' ``a(sa{sv})`` argument from PySide6 (Q13,
``marshal_check.py``), so the portal calls go through ``jeepney``. Only the version check
uses QtDBus, so on a desktop without the portal this runs with just PySide6:

    .venv-1/bin/python -I plans/phase-3/spike/shortcut.py          # GNOME 46: "missing"
    uv run --no-project --with PySide6 --with jeepney \\
        python -I plans/phase-3/spike/shortcut.py --timeout 60 [--register]   # KDE

Every portal request has a timeout (``--timeout``, default 20 s). On timeout it calls
``Request.Close`` (which closes the dialog), prints ``TIMEOUT``, and exits 3. One try,
no retries. Imports nothing from ``kami``.
"""

from __future__ import annotations

import argparse
import secrets
import sys
import time

DESKTOP = "org.freedesktop.portal.Desktop"
DESKTOP_PATH = "/org/freedesktop/portal/desktop"
SHORTCUTS = "org.freedesktop.portal.GlobalShortcuts"
REQUEST = "org.freedesktop.portal.Request"
REGISTRY = "org.freedesktop.host.portal.Registry"
EXIT_TIMEOUT = 3


def say(*parts: object) -> None:
    print(*parts, flush=True)


def portal_version() -> str | None:
    """GlobalShortcuts' version with QtDBus (no QCoreApplication needed, Q12)."""
    from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage, QDBusVariant

    msg = QDBusMessage.createMethodCall(
        DESKTOP, DESKTOP_PATH, "org.freedesktop.DBus.Properties", "Get"
    )
    msg.setArguments([SHORTCUTS, "version"])
    reply = QDBusConnection.sessionBus().call(msg, QDBus.CallMode.Block, 2000)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage or not reply.arguments():
        say(f"GlobalShortcuts: missing ({reply.errorName()})")
        return None
    value = reply.arguments()[0]
    if isinstance(value, QDBusVariant):
        value = value.variant()
    return str(value)


def printable(text: object, cap: int = 60) -> str:
    if not isinstance(text, str):
        return f"<{type(text).__name__}>"
    return "".join(ch for ch in text if ch.isprintable())[:cap]


def error_text(reply) -> str:
    name = reply.header.fields.get(4, "")  # HeaderFields.error_name
    text = reply.body[0] if reply.body else ""
    return f"{printable(name, 80)}: {printable(text, 160)}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--timeout", type=float, default=20.0, help="seconds per request (20)")
    ap.add_argument("--listen", type=float, default=30.0, help="seconds to print Activated")
    ap.add_argument("--register", action="store_true", help="call Registry.Register first")
    opts = ap.parse_args()

    version = portal_version()
    if version is None:
        return 0
    say(f"GlobalShortcuts: v{version}")
    try:
        from jeepney import DBusAddress, MatchRule, message_bus, new_method_call
        from jeepney.io.blocking import Proxy, open_dbus_connection
        from jeepney.low_level import MessageType
    except ImportError:
        say("jeepney is needed for the rest. Run: uv run --no-project --with PySide6 "
            "--with jeepney python -I plans/phase-3/spike/shortcut.py --timeout 60")
        return 2

    conn = open_dbus_connection(bus="SESSION")
    bus = Proxy(message_bus, conn)
    owner = bus.GetNameOwner(DESKTOP)[0]  # jeepney matches the sender's unique name locally
    unique = conn.unique_name
    say(f"our unique name {unique}; portal owner {owner}")
    desktop = DBusAddress(DESKTOP_PATH, bus_name=DESKTOP, interface=SHORTCUTS)

    def request(method: str, signature: str, body: tuple, token: str):
        """Call a Request-returning method; wait for its Response. None on failure."""
        path = f"{DESKTOP_PATH}/request/{unique.lstrip(':').replace('.', '_')}/{token}"
        rule = MatchRule(type="signal", sender=owner, interface=REQUEST, member="Response",
                         path=path)
        bus.AddMatch(rule)
        try:
            with conn.filter(rule) as queue:
                started = time.monotonic()
                reply = conn.send_and_get_reply(
                    new_method_call(desktop, method, signature, body), timeout=5)
                if reply.header.message_type == MessageType.error:
                    say(f"{method} failed: {error_text(reply)}")
                    return None
                say(f"{method}: returned path same as predicted: {reply.body[0] == path}")
                try:
                    got = conn.recv_until_filtered(queue, timeout=opts.timeout)
                except TimeoutError:
                    close = DBusAddress(path, bus_name=DESKTOP, interface=REQUEST)
                    conn.send(new_method_call(close, "Close"))
                    say(f"TIMEOUT (a dialog probably appeared): no {method} Response in "
                        f"{opts.timeout:g} s; sent Request.Close")
                    return "timeout"
                ms = (time.monotonic() - started) * 1000
                say(f"{method} Response after {ms:.0f} ms: signature "
                    f"{got.header.fields.get(8)!r}, body {got.body!r}")
                return got.body
        finally:
            bus.RemoveMatch(rule)

    if opts.register:
        intro = conn.send_and_get_reply(new_method_call(
            DBusAddress(DESKTOP_PATH, bus_name=DESKTOP,
                        interface="org.freedesktop.DBus.Introspectable"), "Introspect"),
            timeout=5)
        if f'interface name="{REGISTRY}"' in str(intro.body[0] if intro.body else ""):
            reg = conn.send_and_get_reply(new_method_call(
                DBusAddress(DESKTOP_PATH, bus_name=DESKTOP, interface=REGISTRY), "Register",
                "sa{sv}", ("org.kami.Kami", {})), timeout=5)
            ok = reg.header.message_type != MessageType.error
            say(f"Registry.Register('org.kami.Kami'): {'ok' if ok else error_text(reg)}")
        else:
            say("Registry.Register: interface missing on this portal")

    token = "kami_spike_" + secrets.token_hex(4)
    created = request("CreateSession", "a{sv}", ({
        "handle_token": ("s", token),
        "session_handle_token": ("s", "kami_spike_s" + secrets.token_hex(4)),
    },), token)
    if not isinstance(created, tuple):
        return EXIT_TIMEOUT if created == "timeout" else 1
    code, results = created
    handle = results.get("session_handle")
    say(f"CreateSession code {code}; session_handle arrives as variant "
        f"{handle[0] if isinstance(handle, tuple) else type(handle).__name__!r}")
    if code != 0 or not isinstance(handle, tuple):
        return 1
    session = handle[1]

    try:
        token = "kami_spike_" + secrets.token_hex(4)
        bound = request("BindShortcuts", "oa(sa{sv})sa{sv}", (
            session,
            [("toggle", {"description": ("s", "Show or hide Kami"),
                         "preferred_trigger": ("s", "CTRL+ALT+k")})],
            "",
            {"handle_token": ("s", token)},
        ), token)
        if not isinstance(bound, tuple):
            return EXIT_TIMEOUT if bound == "timeout" else 1
        code, results = bound
        say(f"BindShortcuts code {code}")
        shortcuts = results.get("shortcuts", ("", []))[1]
        for entry in shortcuts if isinstance(shortcuts, list) else []:
            sid, props = entry
            trigger = props.get("trigger_description", ("s", ""))[1]
            say(f"  bound {printable(sid)!r}: trigger_description {printable(trigger)!r}")
        if code != 0:
            return 4

        say(f"Press the shortcut now; listening for Activated for {opts.listen:g} s")
        rule = MatchRule(type="signal", sender=owner, interface=SHORTCUTS, member="Activated",
                         path=DESKTOP_PATH)
        bus.AddMatch(rule)
        with conn.filter(rule) as queue:
            deadline = time.monotonic() + opts.listen
            while (left := deadline - time.monotonic()) > 0:
                try:
                    sig = conn.recv_until_filtered(queue, timeout=left)
                except TimeoutError:
                    break
                s_handle, sid = sig.body[0], sig.body[1]
                say(f"  Activated {printable(sid)!r}, ours: {s_handle == session}")
        bus.RemoveMatch(rule)
        return 0
    finally:
        closer = DBusAddress(session, bus_name=DESKTOP, interface="org.freedesktop.portal.Session")
        try:
            done = conn.send_and_get_reply(new_method_call(closer, "Close"), timeout=1)
            closed = done.header.message_type != MessageType.error
            say(f"Session.Close: {'ok' if closed else error_text(done)}")
        except TimeoutError:
            say("Session.Close: no reply in 1 s (the portal closes it when we disconnect)")
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
