"""Command line. Parses arguments before anything imports Qt, so `--version` and
`doctor` work over SSH or in a text console with no display.

    kami              start Kami (or toggle it if it's already running)
    kami toggle       show/hide the running Kami (bind this to a desktop shortcut)
    kami doctor       print a health report and exit
    kami --version    print the version and exit
"""
from __future__ import annotations

import argparse
import sys

from kami import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kami", description="A hotkey-summoned AI sidekick for the Linux desktop.")
    parser.add_argument("--version", action="version", version=f"kami {__version__}")
    parser.add_argument(
        "command", nargs="?", default="start", choices=["start", "toggle", "doctor"],
        help="start (default), toggle the running Kami, or doctor (health report)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "doctor":
        from kami.doctor import run_doctor
        return run_doctor()
    from kami.app import main as start_app  # Qt is only imported from here on
    return start_app(["toggle"] if args.command == "toggle" else [])
