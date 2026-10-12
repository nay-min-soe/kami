"""Phase 3 spike, Q8 + Q12: which desktop portals exist, and at which version.

Reads the ``version`` property of the Screenshot, GlobalShortcuts and ScreenCast portals,
and checks whether ``org.freedesktop.host.portal.Registry`` is there (Q8: can an
unsandboxed app give itself an app id?).

    .venv-1/bin/python -I plans/phase-3/spike/portal_versions.py           # with an app
    .venv-1/bin/python -I plans/phase-3/spike/portal_versions.py --no-app  # Q12: without

No dialog, no screenshot, nothing written. Imports nothing from ``kami``.
"""

from __future__ import annotations

import argparse
import sys
import time

from PySide6.QtCore import QCoreApplication
from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage, QDBusVariant

DESKTOP = "org.freedesktop.portal.Desktop"
DESKTOP_PATH = "/org/freedesktop/portal/desktop"
INTERFACES = (
    "org.freedesktop.portal.Screenshot",
    "org.freedesktop.portal.GlobalShortcuts",
    "org.freedesktop.portal.ScreenCast",
)
REGISTRY = "org.freedesktop.host.portal.Registry"


def read_version(bus: QDBusConnection, interface: str, timeout_ms: int) -> tuple[str, float]:
    """One blocking Properties.Get. Returns (printable result, milliseconds)."""
    msg = QDBusMessage.createMethodCall(
        DESKTOP, DESKTOP_PATH, "org.freedesktop.DBus.Properties", "Get"
    )
    msg.setArguments([interface, "version"])
    start = time.monotonic()
    reply = bus.call(msg, QDBus.CallMode.Block, timeout_ms)
    ms = (time.monotonic() - start) * 1000
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        return f"missing ({reply.errorName()}: {reply.errorMessage()[:80]})", ms
    args = reply.arguments()
    if not args:
        return "missing (empty reply)", ms
    value = args[0]
    raw_type = type(value).__name__
    if isinstance(value, QDBusVariant):
        value = value.variant()
    return f"v{value} (reply arg type {raw_type})", ms


def has_registry(bus: QDBusConnection, timeout_ms: int) -> str:
    """Introspect the portal object and look for the host Registry interface."""
    msg = QDBusMessage.createMethodCall(
        DESKTOP, DESKTOP_PATH, "org.freedesktop.DBus.Introspectable", "Introspect"
    )
    reply = bus.call(msg, QDBus.CallMode.Block, timeout_ms)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        return f"unknown ({reply.errorName()})"
    xml = str(reply.arguments()[0]) if reply.arguments() else ""
    return "present" if f'interface name="{REGISTRY}"' in xml else "missing"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-app", action="store_true", help="read before any QCoreApplication")
    ap.add_argument("--timeout", type=float, default=2.0, help="seconds per D-Bus call (2)")
    opts = ap.parse_args()
    timeout_ms = int(opts.timeout * 1000)

    app = None
    if not opts.no_app:
        app = QCoreApplication(sys.argv)
    print("QCoreApplication exists:", QCoreApplication.instance() is not None)

    start = time.monotonic()
    bus = QDBusConnection.sessionBus()
    print(f"sessionBus connected: {bus.isConnected()} "
          f"({(time.monotonic() - start) * 1000:.1f} ms)")
    if not bus.isConnected():
        print("no session bus:", bus.lastError().name())
        return 1

    total = 0.0
    for interface in INTERFACES:
        result, ms = read_version(bus, interface, timeout_ms)
        total += ms
        short = interface.rsplit(".", 1)[-1]
        print(f"{short}: {result} [{ms:.1f} ms]")
    print(f"total for {len(INTERFACES)} reads: {total:.1f} ms")
    print(f"Registry ({REGISTRY}): {has_registry(bus, timeout_ms)}")
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
