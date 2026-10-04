#!/usr/bin/env python3
"""PreToolUse hook: on the first code edit of each user prompt, remind Claude of the explain-first skill."""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

WATCHED = re.compile(r"(^|/)(src/.+\.py|tests/.+\.py|pyproject\.toml)$")

try:
    event = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)

path = (event.get("tool_input") or {}).get("file_path", "")
if not WATCHED.search(path):
    sys.exit(0)

# One reminder per user prompt, not per edit.
turn = event.get("prompt_id") or event.get("session_id") or ""
marker = Path(tempfile.gettempdir()) / f"kami-explain-first-{os.getuid()}" / re.sub(r"\W", "_", turn)
if not turn or marker.exists():
    sys.exit(0)
marker.parent.mkdir(parents=True, exist_ok=True)
marker.touch()

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": f"About to edit code ({path}). Per the explain-first skill, the user must "
                             "have approved a plain-English brief for this change. If they have not, "
                             "stop, write the brief, and wait. Touching more than ~3 files or adding a "
                             "dependency: suggest /backup first.",
    }
}))
