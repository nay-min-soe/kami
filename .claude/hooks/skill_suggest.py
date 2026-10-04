#!/usr/bin/env python3
"""UserPromptSubmit hook: point Claude at the Kami skill that fits what the user just asked."""
import json
import re
import sys

# (pattern, hint). Skills with disable-model-invocation can only be run by the user,
# so for those the hint tells Claude to suggest the slash command instead.
RULES = [
    (r"\b(brainstorm|grill me|think (this |it )?through|stress[- ]test|sparring)\b",
     "Use the brainstorm skill: one sharp question per message."),
    (r"\b(how (should|would|do) (i|we) (build|add|implement|design)|new (feature|mode)|integrat\w*|architect\w*)\b",
     "Use the architecture-advisor skill before any code: options, recommendation, smallest first slice."),
    (r"\b(security|secure|audit|vulnerab\w*|api key|secret|injection|exploit|untrusted)\b",
     "Use the security-check skill on the affected code."),
    (r"\b(review|look over|check my (change|code|diff)s?)\b",
     "If the user wants a code review, tell them to run /kami-review (user-only skill)."),
    (r"\b(clean ?up|tidy|lint|format|refactor for readability)\b",
     "If the user wants a cleanup pass, tell them to run /clean-code (user-only skill)."),
    (r"\b(back ?up|snapshot|restore)\b",
     "If the user wants a snapshot or restore, tell them to run /backup (user-only skill)."),
]

try:
    event = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)

prompt = (event.get("prompt") or "").lower()
if prompt.startswith("/"):
    sys.exit(0)  # the user already picked a skill or command

hints = [hint for pattern, hint in RULES if re.search(pattern, prompt)]
if hints:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "Kami skill hints for this prompt:\n- " + "\n- ".join(hints),
        }
    }))
