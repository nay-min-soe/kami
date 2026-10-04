---
name: docs-sync
description: Update Kami's docs (README.md, config.example.toml, module docstrings) to match code just changed. Use after any edit to src/, tests/, or pyproject.toml, before reporting the task done.
---

# Docs sync

The docs are stale the moment code changes without them. After a code change, bring every doc that describes the changed behaviour back in line with the code.

## Where Kami's docs live

| Doc | What in it goes stale |
|---|---|
| `README.md` → "What it does" table | a mode's status (✅ / 🟡) and one-line description |
| `README.md` → "The safety rule" | any change to `safety.py` or the confirm dialog |
| `README.md` → "Quick start" | install extras in `pyproject.toml`, env var names, Python version |
| `README.md` → "Hotkey: X11 vs Wayland" | `hotkey.py`, `app.py` (`kami toggle`), capture code |
| `README.md` → "Project layout" | any file added, removed, renamed, or whose job changed |
| `README.md` → "Roadmap" | tick `[x]` an item the change finishes; add one the change defers |
| `config.example.toml` | every key `config.py` reads, with a comment saying what it does |
| Module docstrings in `src/kami/**` | the "Status:" / "Plan:" notes (e.g. `meetings.py`) and the handler list in `app_control.py` |

## Steps

1. List what changed: `git diff HEAD --stat` plus `git status --short` for new files.
2. For each changed file, read the diff and find every row of the table above it affects. Search the docs for the changed names too: `grep -rn "<old name>" README.md config.example.toml src/`.
3. Edit the docs so they describe what the code does **now**. Match the existing voice: short, plain, second person, no marketing words.
4. Only describe behaviour that exists in the code. Planned work goes in the Roadmap or a module's "Plan:" note, marked as TODO.
5. Report one line per doc touched, or "Docs already match" with the reason.

Done when every changed file has been checked against every row of the table, and each row it affects reflects the new code.
