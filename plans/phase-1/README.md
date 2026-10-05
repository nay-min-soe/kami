# Phase 1 — Foundation hardening (v0.2)

Goal: make what exists reliable before adding features. See [MILESTONES.md](../../MILESTONES.md).

Baseline (2026-10-05): 10 tests pass, no CI, `ruff` reports 4 issues, LLM errors
reach the panel as raw `httpx` text.

## Tasks

| # | Task | Size | Depends on |
|---|---|---|---|
| 1 | [CI with pytest](task-1-ci.md) | S | — |
| 2 | [Linting with ruff](task-2-ruff.md) | S | 1 |
| 3 | [Plain-language LLM errors](task-3-llm-errors.md) | M | — |
| 4 | [Config validation](task-4-config-validation.md) | S | — |
| 5 | [Logging](task-5-logging.md) | S | — |
| 6 | [Tests for app control and meetings](task-6-test-coverage.md) | S | — |
| 7 | [`kami --version` and `kami doctor`](task-7-version-doctor.md) | M | 3, 4 |

Suggested order: 1 → 2 → 6 → 4 → 3 → 5 → 7. CI comes first so every later task
is checked automatically.

## Rules for every task

- One branch and one PR per task. Commit messages are lowercase and imperative,
  like the existing `add initial scaffold`.
- Code in `modes/`, `llm/`, `config.py` and `safety.py` stays free of Qt, so
  `pytest` runs without a display.
- Run `/security-check` on tasks that touch `llm/`, `config.py` or logging (3, 4, 5, 7).
- Update `README.md` / `config.example.toml` when behaviour changes (`/docs-sync`).
- When a task is done, add a plain-language recap to [task-recaps.md](../task-recaps.md)
  and update [ARCHITECTURE.md](../../ARCHITECTURE.md) if a component changed (`/task-recap`).

## Phase exit criteria

- [ ] CI is green on every push to `main`
- [ ] Every LLM / config error shows a one-line human message in the panel
- [ ] `kami doctor` explains why the hotkey or capture won't work on this machine
