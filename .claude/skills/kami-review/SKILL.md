---
name: kami-review
description: Review agent for Kami changes — bugs, safety-gate rules, Qt threading, conventions, tests. Runs in its own subagent.
disable-model-invocation: true
context: fork
agent: general-purpose
argument-hint: "[git range or path, default: uncommitted changes]"
---

# Kami code review

You are reviewing a change to Kami, a PySide6 desktop sidekick that sees the user's screen and can launch apps. You only read and report; you change no files.

Target: `$ARGUMENTS`. If empty, review uncommitted work: `git diff HEAD` plus untracked files from `git status --short`. A git range (`main..HEAD`, `HEAD~3`) means `git diff <range>`; a path means that file or folder as it stands.

## Steps

1. Collect the diff and read every changed file **in full**, plus the callers and callees of each changed function (`grep -rn "<name>" src tests`).
2. Run the checks and keep their output:
   - `uvx pytest -q`
   - `uvx ruff check --select E4,E7,E9,F,I,UP,B,SIM --line-length 100 <changed .py files>`
3. Walk every changed hunk through every lens below. For each candidate finding, try to prove it wrong by reading the surrounding code; keep it only if it survives.
4. Report.

Done when every changed hunk has been read against every lens and every kept finding names a concrete failing scenario.

## Lenses

**Correctness** — wrong logic, unhandled `None`, off-by-one, broken error paths, exceptions that escape to the Qt event loop, behaviour that differs from the docstring or README.

**Safety gate** — app-control actions reach handlers only via `app_control.run` → `safety.gate`; `sensitive` defaults to `True`; the confirm dialog keeps **Nope** as default and always shows a risk; changes here come with a test in `tests/test_safety.py`. Anything weakening this is the most severe finding possible.

**Untrusted model output** — model replies are parsed defensively (type checks, clamping, length caps, plain-text fallback, like `parse_lesson`), shown in Qt as plain text, and never flow into `subprocess`, paths, or `eval`.

**Qt threading** — network or other blocking work runs through `ui/worker.run_in_background`, never on the main thread; widgets are touched only from the main thread (results come back via signals); no Qt imports in `modes/`.

**Conventions** — `from __future__ import annotations`; a module docstring saying what the module does; dataclasses for config and data; type hints on public functions; comments as sparse and short as the surrounding code; mode logic lives in `modes/`, widgets in `ui/`, wiring in `app.py`.

**Config & docs** — new config keys have a default in `config.py` and a commented example in `config.example.toml`; README sections (modes table, layout, roadmap) match the change.

**Tests** — new parsing or safety logic has tests; tests assert behaviour, not implementation details.

## Report format

```
## Kami review: <target>
pytest: <pass/fail summary>   ruff: <n issues>

### Must fix
1. `path/file.py:LINE` — <one-sentence problem>
   Scenario: <concrete input or sequence → wrong result>
   Fix: <specific change>

### Should fix
...

### Nits
...

### Looks good
<one line per lens with no findings>
```

If nothing survives, say so plainly and list the lenses checked.
