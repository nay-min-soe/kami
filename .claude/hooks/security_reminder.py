#!/usr/bin/env python3
"""PostToolUse hook: after an edit to security-sensitive Kami code, remind Claude to run security-check."""
import json
import re
import sys

# Matches the security-check skill's trigger list: safety gate, app control, LLM client,
# config (API key), the socket in app.py, the confirm dialog, and dependencies.
SENSITIVE = re.compile(
    r"(^|/)(src/kami/(safety\.py|config\.py|app\.py|modes/app_control\.py|llm/.+\.py|ui/confirm\.py)"
    r"|pyproject\.toml)$"
)

try:
    event = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)

path = (event.get("tool_input") or {}).get("file_path", "")
if SENSITIVE.search(path):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": f"Security-sensitive file changed ({path}). Before reporting the task "
                                 "done, run the security-check skill on the change.",
        }
    }))
