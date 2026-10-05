# Task 1 — CI with pytest

**Size:** S · **Depends on:** — · **Branch:** `ci-pytest`

## Goal

Every push and pull request to `main` runs the test suite on Python 3.11 and 3.12.

## Why

Nothing checks the code today. The safety gate is only safe while its tests keep
passing, so a broken test should block a merge.

## Files

| File | Change |
|---|---|
| `.github/workflows/ci.yml` | new |
| `README.md` | CI badge + "Development" section mentions CI |

## Implementation

1. Create `.github/workflows/ci.yml`:
   - Triggers: `push` to `main`, all `pull_request`s.
   - Matrix: `python-version: ["3.11", "3.12"]` on `ubuntu-latest`.
   - Steps: `actions/checkout`, `actions/setup-python` with `cache: pip`,
     `pip install -e ".[dev]"`, `pytest -q`.
2. Keep tests free of a display. The current suite only imports `config`,
   `safety` and `modes.learning`, which have no Qt imports, so no `xvfb` is needed.
   If a future test needs Qt, add `QT_QPA_PLATFORM=offscreen` to that job, not globally.
3. Optional speed-up: PySide6 is a large download. If installs are slow, add a `test`
   extra with only `httpx` + `pytest` and install `-e ".[test]" --no-deps` plus `httpx`.
   Only do this if the install step takes more than about 60 s.
4. Add the badge to the top of `README.md`.

## Tests

The workflow is the test. Check it both ways:

- [ ] Open a PR with the workflow: both matrix jobs pass.
- [ ] Push a throwaway commit that breaks `test_safety.py` (e.g. `assert False`):
      the PR shows a red check. Then close that PR.

## Done when

- [ ] Both Python versions run on every PR and push to `main`
- [ ] A failing test turns the check red
- [ ] (Optional, in GitHub settings) branch protection on `main` requires the check

## Commit

`add ci workflow running pytest`
