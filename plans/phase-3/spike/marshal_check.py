"""Phase 3 spike, Q13 (and the slot half of Q1): what PySide6 QtDBus can send and read.

GNOME 46 has no GlobalShortcuts portal, so this tests on our own service instead:

1. A child process registers ``org.kami.Spike`` with one object, ``/org/kami/Spike``,
   whose ``Echo`` method takes and returns ``(o, a(sa{sv}), a{sv})`` and whose
   ``EchoLast`` method returns the last ``Echo`` arguments again.
2. Three child processes try to *send* ``a(sa{sv})`` from QtDBus three ways (A, B, C),
   and print the wire signature that came back. Each runs on its own, with a kill
   timeout, because a wrong struct array makes libdbus abort and a failed marshal can
   leave the connection stuck.
3. ``gdbus`` sends the real ``a(sa{sv})``; the service prints what QtDBus received.
4. ``EchoLast`` brings the same values back to *this* process as a method reply, and
   ``gdbus emit`` sends a ``Response(u, a{sv})`` and an ``Activated(o, s, t, a{sv})``
   signal. Both slot styles are connected: a typed ``(uint, QVariantMap)`` slot and a
   ``QDBusMessage`` slot. Every part's Python type is printed, and each
   ``QDBusArgument`` is read with the calls PySide6 offers.
5. One more signal on the same path from a sender that isn't ``org.kami.Spike`` checks
   that a slot connected with a service name ignores other senders.
6. ``Quit`` makes the service unregister; this process checks the name is gone.

    .venv-1/bin/python -I plans/phase-3/spike/marshal_check.py [--timeout 20]

Nothing here touches a portal, the screen or a file. Imports nothing from ``kami``.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time

from PySide6.QtCore import SLOT, QCoreApplication, QEventLoop, QObject, QTimer, Slot
from PySide6.QtDBus import (
    QDBus,
    QDBusArgument,
    QDBusConnection,
    QDBusMessage,
    QDBusObjectPath,
    QDBusVariant,
    QDBusVirtualObject,
)

SERVICE = "org.kami.Spike"
PATH = "/org/kami/Spike"
IFACE = "org.kami.Spike"
TEST_PATH = "/org/kami/test"
SHORTCUT = {"description": "Show or hide Kami", "preferred_trigger": "CTRL+ALT+k"}
# The same values in GVariant text, for gdbus (QtDBus can't send them, see A/B/C).
GV_PATH = f"objectpath '{TEST_PATH}'"
GV_SHORTCUTS = (
    "[('toggle', {'description': <'Show or hide Kami'>, "
    "'preferred_trigger': <'CTRL+ALT+k'>})]"
)
GV_OPTIONS = f"{{'session_handle': <objectpath '{TEST_PATH}'>}}"
GV_RESULTS = (
    "{'uri': <'file:///nonexistent/kami-spike.png'>, "
    f"'session_handle': <objectpath '{TEST_PATH}'>, "
    "'shortcuts': <[('toggle', {'description': <'Show or hide Kami'>, "
    "'trigger_description': <'Ctrl+Alt+K'>})]>}"
)
INTROSPECT = f"""<interface name="{IFACE}">
  <method name="Echo">
    <arg type="o" direction="in"/><arg type="a(sa{{sv}})" direction="in"/>
    <arg type="a{{sv}}" direction="in"/>
    <arg type="o" direction="out"/><arg type="a(sa{{sv}})" direction="out"/>
    <arg type="a{{sv}}" direction="out"/>
  </method>
  <method name="EchoLast">
    <arg type="o" direction="out"/><arg type="a(sa{{sv}})" direction="out"/>
    <arg type="a{{sv}}" direction="out"/>
  </method>
  <method name="EmitTest"/>
  <method name="Quit"/>
</interface>
"""
MAX_ITEMS = 8  # every read loop is capped: a wrong PySide overload never reaches atEnd()


def say(*parts: object) -> None:
    print(*parts, flush=True)


def describe(value: object, depth: int = 0) -> str:
    """Python type of a value, and of what's inside it, without reading QDBusArgument."""
    name = type(value).__name__
    if depth > 3:
        return name
    if isinstance(value, QDBusArgument):
        return f"QDBusArgument[{value.currentSignature()}, {value.currentType().name}]"
    if isinstance(value, QDBusVariant):
        return f"QDBusVariant({describe(value.variant(), depth + 1)})"
    if isinstance(value, QDBusObjectPath):
        return f"QDBusObjectPath({value.path()!r})"
    if isinstance(value, dict):
        inner = ", ".join(f"{k!r}: {describe(v, depth + 1)}" for k, v in value.items())
        return f"dict{{{inner}}}"
    if isinstance(value, (list, tuple)):
        inner = ", ".join(describe(v, depth + 1) for v in value)
        return f"{name}[{inner}]"
    return f"{name}({value!r})"


def try_read(arg: QDBusArgument) -> str:
    """Read a QDBusArgument with PySide6's calls; report how far it gets. Never loops."""
    kind = arg.currentType()
    sig = arg.currentSignature()
    ET = QDBusArgument.ElementType
    if kind == ET.ArrayType:
        arg.beginArray()  # no-arg overload: only the read version exists in C++
        items = []
        while not arg.atEnd() and len(items) < MAX_ITEMS:
            items.append(arg.asVariant())
        parts = [describe(i) for i in items]
        if items and isinstance(items[0], QDBusArgument):
            parts.append("element 0 -> " + try_read(items[0]))
        return f"{sig}: beginArray() ok, {len(items)} item(s): " + "; ".join(parts)
    if kind == ET.StructureType:
        arg.beginStructure()  # read and write overloads look alike; see what PySide picks
        moved = arg.currentSignature() != sig
        return f"{sig}: beginStructure() {'entered' if moved else 'did not enter (write overload)'}"
    if kind == ET.MapType:
        arg.beginMap()
        entry = arg.asVariant() if not arg.atEnd() else None
        return f"{sig}: beginMap() ok, first entry via asVariant() -> {describe(entry)}"
    return f"{sig}: {kind.name}, asVariant() -> {describe(arg.asVariant())}"


# --- the service (child process) -------------------------------------------------------


class EchoObject(QDBusVirtualObject):
    def __init__(self, bus: QDBusConnection, app: QCoreApplication) -> None:
        super().__init__()
        self._bus = bus
        self._app = app
        self._last: list = []

    def introspect(self, path: str) -> str:
        return INTROSPECT

    def handleMessage(self, message: QDBusMessage, connection: QDBusConnection) -> bool:
        member = message.member()
        if message.interface() != IFACE:
            return False
        if member == "Echo":
            args = message.arguments()
            say(f"  [service] Echo wire signature {message.signature()!r}")
            say(f"  [service] received: {[describe(a) for a in args]}")
            self._last = args
            reply = message.createReply()
            reply.setArguments(args)  # a received QDBusArgument is re-sent as it came
            connection.send(reply)
            return True
        if member == "EchoLast":
            reply = message.createReply()
            reply.setArguments(self._last)
            connection.send(reply)
            return True
        if member == "EmitTest":  # a plain signal from the name's owner (for jeepney's filter)
            connection.send(message.createReply())
            sig = QDBusMessage.createSignal(PATH, IFACE, "Response")
            sig.setArguments([0, {"uri": "file:///nonexistent/kami-spike.png"}])
            connection.send(sig)
            return True
        if member == "Quit":
            connection.send(message.createReply())
            QTimer.singleShot(0, self._app.quit)
            return True
        return False


def serve(timeout_s: float) -> int:
    app = QCoreApplication(sys.argv)
    bus = QDBusConnection.sessionBus()
    obj = EchoObject(bus, app)
    bus.registerVirtualObject(PATH, obj)  # the object first, so no caller finds the name early
    if not bus.registerService(SERVICE):
        say("  [service] could not register", SERVICE, bus.lastError().name())
        return 1
    say(f"  [service] registered {SERVICE}")
    QTimer.singleShot(int(timeout_s * 1000), app.quit)  # never outlive the check
    app.exec()
    bus.unregisterObject(PATH)
    ok = bus.unregisterService(SERVICE)
    say(f"  [service] unregistered {SERVICE}: {ok}")
    return 0


def send_child(case: str) -> int:
    """Send ``a(sa{sv})`` from QtDBus one way (A, B or C), in a process of its own.

    A wrong struct array makes libdbus abort (C), and a failed marshal can leave the
    connection stuck (A), so the parent runs each case here, with a kill timeout.
    """
    QCoreApplication(sys.argv)
    bus = QDBusConnection.sessionBus()
    path = QDBusObjectPath(TEST_PATH)
    if case == "A":
        shortcuts: object = [("toggle", dict(SHORTCUT))]
    elif case == "B":
        shortcuts = [["toggle", dict(SHORTCUT)]]
    else:
        from PySide6.QtCore import QMetaType

        one = QDBusArgument()
        one.beginStructure()
        one << "toggle"
        one << dict(SHORTCUT)
        one.endStructure()
        say(f"  [C] one (s, a{{sv}}) structure written as {one.currentSignature()!r}")
        arr = QDBusArgument()
        arr.beginArray(QMetaType(QMetaType.Type.QVariantMap))
        say("  [C] beginArray(QVariantMap) ok; writing a structure element next")
        arr.beginStructure()
        arr << "toggle"
        arr << dict(SHORTCUT)
        arr.endStructure()
        arr.endArray()
        say(f"  [C] array written as {arr.currentSignature()!r}")
        shortcuts = arr
    reply = call(bus, "Echo", [path, shortcuts, {"session_handle": path}], 3000)
    show_reply(f"  [{case}] Echo", reply)
    if case == "A":
        say("  [A] one more call on the same connection (EchoLast, 3 s timeout)...")
        show_reply("  [A] EchoLast", call(bus, "EchoLast", [], 3000))
    return 0


# --- the client (this process) ---------------------------------------------------------


class Receiver(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.got: list[str] = []

    @Slot("uint", "QVariantMap")  # D-Bus "u" needs a uint slot; int is refused
    def typed_response(self, code: int, results: dict) -> None:
        self.got.append("typed")
        say(f"  typed slot (uint, QVariantMap): code {describe(code)}")
        say(f"    results: {describe(results)}")
        for key, value in results.items():
            if isinstance(value, QDBusArgument):
                say(f"    read {key!r}: {try_read(value)}")

    @Slot(QDBusMessage)
    def message_response(self, message: QDBusMessage) -> None:
        self.got.append("message")
        args = message.arguments()
        say(f"  QDBusMessage slot: sender {message.service()}, "
            f"signature {message.signature()!r}")
        say(f"    arguments(): {[describe(a) for a in args]}")
        for a in args:
            if isinstance(a, QDBusArgument):
                say(f"    read: {try_read(a)}")

    @Slot(QDBusMessage)
    def activated(self, message: QDBusMessage) -> None:
        self.got.append("activated")
        say(f"  Activated signature {message.signature()!r}")
        say(f"    arguments(): {[describe(a) for a in message.arguments()]}")

    @Slot(QDBusMessage)
    def filtered(self, message: QDBusMessage) -> None:
        self.got.append("filtered")
        say(f"  slot filtered on {SERVICE} fired (sender {message.service()}, "
            f"signature {message.signature()!r})")


def wait(ms: int, until=None) -> None:
    loop = QEventLoop()
    deadline = time.monotonic() + ms / 1000
    while time.monotonic() < deadline:
        loop.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        if until is not None and until():
            return
        time.sleep(0.01)


def call(bus: QDBusConnection, member: str, args: list, timeout_ms: int) -> QDBusMessage:
    msg = QDBusMessage.createMethodCall(SERVICE, PATH, IFACE, member)
    msg.setArguments(args)
    return bus.call(msg, QDBus.CallMode.Block, timeout_ms)


def show_reply(label: str, reply: QDBusMessage) -> None:
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        say(f"{label}: error {reply.errorName()}: {reply.errorMessage()[:100]}")
    else:
        say(f"{label}: reply signature {reply.signature()!r}")


def run_gdbus(gdbus: str, args: list[str], timeout_s: float) -> str:
    done = subprocess.run(
        [gdbus, *args], capture_output=True, text=True, timeout=timeout_s, check=False
    )
    return (done.stdout.strip() or done.stderr.strip())[:300]


def jeepney_check(gdbus: str, timeout_s: float) -> None:
    """Send and read the same values with jeepney, if it's installed (never required)."""
    try:
        from jeepney import DBusAddress, MatchRule, message_bus, new_method_call
        from jeepney.io.blocking import Proxy, open_dbus_connection
    except ImportError:
        say("  jeepney not installed: skipped (run with `uv run --no-project --with PySide6 "
            "--with jeepney python -I ...` to include it)")
        return
    import jeepney

    conn = open_dbus_connection(bus="SESSION")
    try:
        spike = DBusAddress(PATH, bus_name=SERVICE, interface=IFACE)
        body = (TEST_PATH,
                [("toggle", {k: ("s", v) for k, v in SHORTCUT.items()})],
                {"session_handle": ("o", TEST_PATH)})
        reply = conn.send_and_get_reply(
            new_method_call(spike, "Echo", "oa(sa{sv})a{sv}", body), timeout=timeout_s)
        say(f"  jeepney {jeepney.__version__}: Echo reply signature "
            f"{reply.header.fields.get(jeepney.HeaderFields.signature)!r}")
        say(f"  reply body: {reply.body!r}")
        say(f"  same values back: {reply.body == body}")
        bus = Proxy(message_bus, conn)
        any_sender = MatchRule(type="signal", interface=IFACE, member="Response", path=PATH)
        bus.AddMatch(any_sender)
        with conn.filter(any_sender) as queue:
            run_gdbus(gdbus, ["emit", "--session", "--object-path", PATH,
                              "--signal", f"{IFACE}.Response", "uint32 0", GV_RESULTS], timeout_s)
            got = conn.recv_until_filtered(queue, timeout=3)
            say(f"  Response from gdbus read back: {got.body!r}")
        bus.RemoveMatch(any_sender)

        owner = bus.GetNameOwner(SERVICE)[0]
        by_name = MatchRule(type="signal", sender=SERVICE, interface=IFACE, member="Response",
                            path=PATH)
        by_owner = MatchRule(type="signal", sender=owner, interface=IFACE, member="Response",
                             path=PATH)
        bus.AddMatch(by_owner)
        with conn.filter(by_owner) as queue:
            conn.send_and_get_reply(new_method_call(spike, "EmitTest"), timeout=timeout_s)
            try:
                got = conn.recv_until_filtered(queue, timeout=3)
                say(f"  signal from the {SERVICE} owner: {got.body!r}")
                say(f"  local match with sender={SERVICE!r}: {by_name.matches(got)}; "
                    f"with the owner's unique name: {by_owner.matches(got)}")
            except TimeoutError:
                say("  no signal from the service owner within 3 s")
        bus.RemoveMatch(by_owner)
    finally:
        conn.close()


def client(timeout_s: float) -> int:
    app = QCoreApplication(sys.argv)
    bus = QDBusConnection.sessionBus()
    gdbus = shutil.which("gdbus")
    if gdbus is None:
        say("gdbus not found (package libglib2.0-bin); steps 3-5 need it")
        return 1
    if bus.interface().isServiceRegistered(SERVICE).value():
        say(f"{SERVICE} is already on the bus; is another marshal_check running?")
        return 1

    child = subprocess.Popen([sys.executable, "-I", __file__, "--serve",
                              "--timeout", str(timeout_s)])
    try:
        wait(5000, lambda: bus.interface().isServiceRegistered(SERVICE).value())
        if not bus.interface().isServiceRegistered(SERVICE).value():
            say("the service didn't come up within 5 s")
            return 1
        ms = int(timeout_s * 1000)

        say("\n== 2. send a(sa{sv}) from QtDBus")
        labels = {
            "A": "[('toggle', {...})], a list of tuples",
            "B": "[['toggle', {...}]], a list of lists",
            "C": "QDBusArgument with beginArray + beginStructure",
        }
        for case, label in labels.items():
            say(f"{case}  {label}")
            try:
                done = subprocess.run(
                    [sys.executable, "-I", __file__, "--send", case],
                    capture_output=True, text=True, timeout=8, check=False,
                )
            except subprocess.TimeoutExpired as stuck:
                out = stuck.stdout or b""
                text = out.decode(errors="replace") if isinstance(out, bytes) else out
                for line in text.strip().splitlines()[:6]:
                    say(line)
                say("   -> still blocked after 8 s although every call has a 3 s timeout: "
                    "stuck, killed")
                continue
            for line in (done.stdout + done.stderr).strip().splitlines()[:8]:
                say(line)
            note = " (killed by a signal: libdbus aborted)" if done.returncode < 0 else ""
            say(f"   -> exit code {done.returncode}{note}")

        say("\n== 3. gdbus sends the real (o, a(sa{sv}), a{sv})")
        out = run_gdbus(gdbus, ["call", "--session", "--dest", SERVICE, "--object-path", PATH,
                                "--method", f"{IFACE}.Echo", GV_PATH, GV_SHORTCUTS, GV_OPTIONS],
                        timeout_s)
        wait(300)
        say(f"  gdbus got the echo back: {out}")

        say("\n== 4a. the same values as a method reply to QtDBus (EchoLast)")
        reply = call(bus, "EchoLast", [], ms)
        show_reply("EchoLast", reply)
        parts = reply.arguments()
        say(f"  arguments(): {[describe(a) for a in parts]}")
        for a in parts:
            if isinstance(a, QDBusArgument):
                say(f"  read: {try_read(a)}")

        say("\n== 4b. signals: Response(u, a{sv}) and Activated(o, s, t, a{sv})")
        recv = Receiver()
        # Any sender (""), because gdbus emits from its own connection. Step 5 tests the filter.
        ok_typed = bus.connect("", PATH, IFACE, "Response", recv,
                               SLOT("typed_response(uint,QVariantMap)"))
        ok_msg = bus.connect("", PATH, IFACE, "Response", recv,
                             SLOT("message_response(QDBusMessage)"))
        ok_act = bus.connect("", PATH, IFACE, "Activated", recv, SLOT("activated(QDBusMessage)"))
        ok_filter = bus.connect(SERVICE, PATH, IFACE, "Response", recv,
                                SLOT("filtered(QDBusMessage)"))
        say(f"  connect: typed {ok_typed}, message {ok_msg}, activated {ok_act}, "
            f"filtered-on-{SERVICE} {ok_filter}")
        run_gdbus(gdbus, ["emit", "--session", "--object-path", PATH,
                          "--signal", f"{IFACE}.Response", "uint32 0", GV_RESULTS], timeout_s)
        run_gdbus(gdbus, ["emit", "--session", "--object-path", PATH,
                          "--signal", f"{IFACE}.Activated", GV_PATH, "'toggle'",
                          "uint64 1234", "@a{sv} {}"], timeout_s)
        wait(min(ms, 3000), lambda: {"typed", "message", "activated"} <= set(recv.got))

        say("\n== 5. sender filter")
        say(f"  slot connected with service {SERVICE!r} fired for gdbus's signal: "
            f"{'filtered' in recv.got}")
        say(f"  slots that fired: {sorted(set(recv.got))}")
        recv.got.clear()
        call(bus, "EmitTest", [], ms)  # now a signal from the name's real owner
        wait(min(ms, 3000), lambda: "filtered" in recv.got)
        say(f"  same slot fired for a signal from the {SERVICE} owner: {'filtered' in recv.got}")
        for name, slot in (("Response", "typed_response(uint,QVariantMap)"),
                           ("Response", "message_response(QDBusMessage)"),
                           ("Activated", "activated(QDBusMessage)")):
            bus.disconnect("", PATH, IFACE, name, recv, SLOT(slot))
        bus.disconnect(SERVICE, PATH, IFACE, "Response", recv, SLOT("filtered(QDBusMessage)"))

        say("\n== 6. jeepney (optional fallback for Task 6)")
        jeepney_check(gdbus, timeout_s)

        say("\n== 7. unregister")
        call(bus, "Quit", [], ms)
        child.wait(timeout=timeout_s)
        wait(300)
        gone = not bus.interface().isServiceRegistered(SERVICE).value()
        say(f"{SERVICE} gone from the bus: {gone}")
        return 0 if gone else 1
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=5)
        del app


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--timeout", type=float, default=20.0, help="seconds (20)")
    ap.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--send", choices="ABC", help=argparse.SUPPRESS)
    opts = ap.parse_args()
    if opts.serve:
        return serve(opts.timeout)
    if opts.send:
        return send_child(opts.send)
    return client(opts.timeout)


if __name__ == "__main__":
    sys.exit(main())
