"""TTY-aware progress messages for operator-facing lab scenarios."""

from __future__ import annotations

import os
import sys


_COLOR = sys.stderr.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
_RESET = "\033[0m" if _COLOR else ""
_COLORS = {
    "section": "\033[1;94m" if _COLOR else "",
    "action": "\033[1;96m" if _COLOR else "",
    "wait": "\033[1;93m" if _COLOR else "",
    "pass": "\033[1;92m" if _COLOR else "",
    "note": "\033[1;94m" if _COLOR else "",
}


def _emit(kind: str, prefix: str, message: str) -> None:
    print(f"{_COLORS[kind]}{prefix}{message}{_RESET}", file=sys.stderr, flush=True)


def section(message: str) -> None:
    _emit("section", "\n=== ", f"{message} ===")


def action(message: str) -> None:
    _emit("action", "==> ", message)


def waiting(message: str) -> None:
    _emit("wait", "... ", message)


def passed(message: str) -> None:
    _emit("pass", "OK: ", message)


def note(message: str) -> None:
    _emit("note", "    ", message)
