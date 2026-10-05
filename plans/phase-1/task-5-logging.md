# Task 5 — Logging

**Size:** S · **Depends on:** — (pairs well with Task 3) · **Branch:** `logging`

## Goal

When something goes wrong, there is a log file to look at, and it never contains
the API key, screenshots, or what the user typed.

## Design

- Path: `$XDG_STATE_HOME/kami/kami.log`, default `~/.local/state/kami/kami.log`.
- `logging.handlers.RotatingFileHandler`, 1 MB × 3 files. Also log to stderr at
  `WARNING` and above.
- Level from the env var `KAMI_LOG_LEVEL` (default `INFO`). No config key for now,
  to keep Task 4 small.
- **What to log:** startup (version, session type, hotkey status), which mode ran,
  model name, request duration, error `kind` (from Task 3), app-control decisions
  (action kind, app, allowed / refused / confirmed / cancelled).
- **What never to log:** API keys, `Authorization` headers, image bytes or base64,
  prompt text, model replies, transcripts.
- Belt and braces: a `logging.Filter` that replaces anything that looks like a key
  (`sk-[A-Za-z0-9_-]{10,}`) and the configured key value with `[redacted]`.

## Files

| File | Change |
|---|---|
| `src/kami/logs.py` | new: `setup_logging(state_dir=None) -> Path`, `RedactKeys` filter |
| `src/kami/app.py` | call `setup_logging()` first thing in `main()` and log startup |
| `src/kami/llm/client.py` | `log = logging.getLogger(__name__)`; log model, duration, error kind |
| `src/kami/modes/app_control.py` | log gate outcome per action |
| `src/kami/ui/worker.py` | log the exception type when a task fails (`log.exception` keeps the traceback in the file, not the UI) |
| `README.md` | "Troubleshooting: logs are in ~/.local/state/kami/kami.log" |

Name the module `logs.py`, not `logging.py`, so it doesn't shadow the standard library.

## Implementation

1. `setup_logging` creates the directory with mode `0o700` and attaches the
   handlers plus the redaction filter to the `kami` logger (not the root logger,
   so PySide6 and httpx stay quiet).
2. Set httpx's own logger to `WARNING`: at `INFO` it logs request URLs.
3. Use `%`-style lazy logging (`log.info("model=%s took=%.1fs", ...)`).

## Tests — `tests/test_logs.py`

- [ ] `test_creates_log_file_in_state_dir`: use `tmp_path`, log one line, and the file exists with it
- [ ] `test_log_dir_is_private`: the directory mode is `0o700`
- [ ] `test_redacts_key_patterns`: `log.info("key sk-or-abc123def456ghi")` writes `[redacted]` to the file
- [ ] `test_redacts_configured_key`: a key without the `sk-` prefix is still redacted when passed to the filter
- [ ] `test_llm_error_logs_kind_not_body`: with Task 3's `MockTransport`, a 401 logs `auth` and does not log the prompt text (use `caplog`)
- [ ] `test_app_control_logs_refusal`: `run()` with confirm returning False logs "cancelled" with app and kind
- [ ] Use `caplog` or a temporary handler, and remove handlers afterwards so tests don't leak into each other

## Manual check

- [ ] Run `kami`, ask a question, explain a region, then read the log: there are
      events and durations, but no prompt, reply, key or base64

## Done when

- [ ] The log file exists after the first run and rotates at 1 MB
- [ ] A search of the log for the API key and for `base64` finds nothing
- [ ] `/security-check` run on the diff

## Commit

`add file logging with key redaction`
