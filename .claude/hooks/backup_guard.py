#!/usr/bin/env python3
"""PreToolUse hook: ask the user before a Bash command that can destroy uncommitted work, pointing at /backup."""
import json
import re
import sys

DESTRUCTIVE = re.compile(
    r"\brm\s+-\w*[rf]"                      # rm -r / rm -rf / rm -f
    r"|\bgit\s+reset\s+--hard\b"
    r"|\bgit\s+clean\s+-\w*f"
    r"|\bgit\s+checkout\s+(--\s|\.(\s|$))"
    r"|\bgit\s+restore\b(?!.*--staged)"
    r"|\bgit\s+stash\s+(drop|clear)\b"
    r"|\bgit\s+branch\s+-D\b"
    r"|\bgit\s+push\s+.*--force"
)

try:
    event = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)

command = (event.get("tool_input") or {}).get("command", "")
# The backup skill's own restore runs after it has taken a fresh snapshot.
if "refs/backups/" in command or not DESTRUCTIVE.search(command):
    sys.exit(0)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": "This command can delete or overwrite work that git may not be able "
                                    "to bring back. Run /backup first if unsure.",
        "additionalContext": "A destructive command was flagged. If the user has not taken a snapshot, "
                             "suggest /backup before going ahead.",
    }
}))
