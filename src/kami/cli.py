"""Command line. Parses arguments before anything imports Qt, so `--version` works
over SSH or in a text console with no display.

    kami              start Kami (or toggle it if it's already running)
    kami toggle       show/hide the running Kami (bind this to a desktop shortcut)
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
        "command", nargs="?", default="start", choices=["start", "toggle"],
        help="start (default) or toggle the running Kami")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    from kami.app import main as start_app  # Qt is only imported from here on
    return start_app(["toggle"] if args.command == "toggle" else [])
