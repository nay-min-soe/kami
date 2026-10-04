#!/usr/bin/env python3
"""PostToolUse hook: after an edit to Kami's code, remind Claude to run the docs-sync skill."""
import json
import re
import sys

WATCHED = re.compile(r"(^|/)(src/kami/.+\.py|pyproject\.toml)$")

try:
    event = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)

path = (event.get("tool_input") or {}).get("file_path", "")
if WATCHED.search(path):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": f"Code changed ({path}). Before reporting the task done, "
                                 "run the docs-sync skill so README.md and config.example.toml match, "
                                 "then suggest the user run /kami-review on the change.",
        }
    }))
