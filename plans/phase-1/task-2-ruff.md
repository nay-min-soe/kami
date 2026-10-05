# Task 2 — Linting with ruff

**Size:** S · **Depends on:** Task 1 · **Branch:** `lint-ruff`

## Goal

`ruff check` runs locally and in CI, and the codebase starts clean.

## Current state

With `--line-length 100 --select E,F,I,UP,B` ruff reports 4 issues:

| File | Rule | Fix |
|---|---|---|
| `src/kami/modes/app_control.py:10` | UP035 | import `Callable` from `collections.abc` |
| `src/kami/safety.py:11` | UP035 | same |
| `src/kami/ui/overlay.py:2` | I001 | sort imports (auto-fix) |
| `tests/test_learning.py:28` | UP031 | use an f-string or `.format` instead of `%` |

No line is longer than 100 characters, so `line-length = 100` fits the current style.

## Files

| File | Change |
|---|---|
| `pyproject.toml` | add `ruff` to `dev` extra; add `[tool.ruff]` config |
| `.github/workflows/ci.yml` | add a lint step before `pytest` |
| the 4 files above | fixes |
| `README.md` | "Development" section: `ruff check .` |

## Implementation

1. `pyproject.toml`:
   ```toml
   [project.optional-dependencies]
   dev = ["pytest>=8", "ruff>=0.6"]

   [tool.ruff]
   line-length = 100
   target-version = "py311"

   [tool.ruff.lint]
   select = ["E", "F", "I", "UP", "B"]
   ```
2. Run `ruff check --fix .`, then fix the `%` format in `tests/test_learning.py` by hand.
   Note that the test builds a JSON string, so an f-string needs doubled braces.
   `.format` or string concatenation may read better.
3. Do **not** run `ruff format` in this task. Reformatting every file would bury
   the real changes. If you want it, do it later as a separate format-only commit.
4. CI: add `- run: ruff check .` before `pytest` (once is enough, e.g. only on 3.12).

## Tests

- [ ] `ruff check .` exits 0 locally.
- [ ] `pytest` still passes (10 tests).
- [ ] CI shows the lint step, and it fails on a PR that adds an unused import.

## Done when

- [ ] `ruff check .` is clean and runs in CI
- [ ] No behaviour change (diff is imports and one string only)

## Commits

1. `add ruff config and ci step`
2. `fix ruff findings`
