---
name: clean-code
description: Clean up Kami code — ruff lint/format plus a by-hand tidy pass, with a backup first and tests after. Behaviour stays the same.
disable-model-invocation: true
argument-hint: "[path | all, default: files changed since HEAD]"
---

# Clean code

Target: `$ARGUMENTS`.
- empty → the `.py` files in `git diff HEAD --name-only` plus untracked `.py` files
- a path → that file or folder
- `all` → `src tests`

Cleaning is a **pure refactor**: what Kami does stays identical; only how the code reads changes.

## Steps

1. **Resolve the target** to a concrete file list and show it. If the list is empty, say so and stop.
2. **Backup**: `.claude/skills/backup/backup.sh before-clean-code`. Report the ref name; it is the undo.
3. **Baseline**: `uvx pytest -q`. If tests already fail, report which and ask whether to continue.
4. **Lint**: `uvx ruff check --fix --select E4,E7,E9,F,I,UP,B,SIM --line-length 100 <files>`. Report what it fixed and what it could not; fix the rest by hand in step 6.
5. **Format**: `uvx ruff format --line-length 100 <files>`. With `all`, first warn that this reformats most of the repo (around 100 lines) and get a yes.
6. **Tidy by hand**, reading each file in full:
   - unused or dead code, unreachable branches, leftover debug `print`s
   - duplicated logic that a small helper in the same module would remove
   - names that don't say what the thing is
   - functions doing two jobs, split only when it makes both halves clearer
   - comments that restate the code, or are stale
   - Kami conventions: `from __future__ import annotations`, a module docstring, type hints on public functions, dataclasses for structured data, no Qt imports in `modes/`

   Leave public names, config keys, and `kami.safety` behaviour as they are; those need an `explain-first` brief, not a cleanup.
7. **Verify**: `uvx pytest -q` must match the baseline. If it got worse, undo that file with `git restore --source=refs/backups/<ref> -- <file>` and report it.
8. **Report** in three parts: what ruff fixed, what you tidied by hand (one line per file), and the backup ref to undo everything. Leave the changes uncommitted for the user to review with `git diff`.

Done when every file in the list has been through steps 4–6 and tests match the baseline.
