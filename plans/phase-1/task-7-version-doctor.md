# Task 7 — `kami --version` and `kami doctor`

**Size:** M · **Depends on:** Task 3 (error kinds), Task 4 (config errors + warnings) · **Branch:** `cli-doctor`

## Goal

A user who reports "Kami doesn't work" can run one command and paste the output.
It says what works, what doesn't, and why.

## Current state

- `app.main()` creates a `QApplication` **before** reading `argv`, so even a simple
  command needs a display. `--version` and `doctor` must work over SSH or in a TTY.
- The only subcommand is `toggle`. Anything else (e.g. `kami --help`) silently starts Kami.

## Design

Parse `argv` with `argparse` **before** importing or creating anything from Qt:

```
kami              start (or toggle the running instance)
kami toggle       show/hide the running instance
kami doctor       print a health report and exit
kami --version    print "kami 0.1.0" and exit
```

`kami doctor` output (example):

```
Kami 0.2.0 · Python 3.12.3
Session       wayland (XDG_SESSION_TYPE)
Config        ~/.config/kami/config.toml  ✓ loaded
              ⚠ unknown key 'allowed_app' — did you mean 'allowed_apps'?
API key       ✓ set (from OPENROUTER_API_KEY)
Endpoint      https://openrouter.ai/api/v1  ✓ reachable
Model         openrouter/auto  ✓ listed · images: unknown
Hotkey        ✗ Wayland can't grab global keys → bind a desktop shortcut to `kami toggle`
Screen grab   ⚠ Wayland: Explain screen may capture a blank image (portal support is Phase 3)
Running       ✓ an instance is answering on the local socket
Log file      ~/.local/state/kami/kami.log
```

Rules:
- Never print the key or any part of it. Say only which source it came from.
- The endpoint check uses `GET {base_url}/models` (OpenAI-compatible, no tokens
  spent). **Never** send a chat request from `doctor`, because that costs the user money.
- Every check has a 5 s timeout, and one failure never stops the report.
- Exit code 0 if everything is ✓ or ⚠, 1 if anything is ✗.

**Check before building:** whether OpenRouter's `/models` response states image
input per model (it may be under an `architecture` field). Confirm with a real call.
If it isn't reliable, print `images: unknown` rather than guessing.

## Files

| File | Change |
|---|---|
| `src/kami/cli.py` | new: `argparse` parser, dispatch |
| `src/kami/doctor.py` | new: `Check` dataclass (`name`, `status`, `detail`), one function per check, `render(checks) -> str`. No Qt at module level |
| `src/kami/app.py` | `main()` calls the parser first and imports Qt only for `start`/`toggle` |
| `src/kami/llm/client.py` | `list_models() -> list[dict]` using the same error mapping as Task 3 |
| `pyproject.toml` | entry point stays `kami.app:main` (or moves to `kami.cli:main`; pick one) |
| `README.md` | document `kami doctor` under Troubleshooting |

The "Running" check needs `QLocalSocket`. Import it inside that one function and
report "skipped" if Qt can't load.

## Tests — `tests/test_cli.py`, `tests/test_doctor.py`

- [ ] `test_version_prints_and_exits_without_qt`: run `main(["--version"])`, check stdout has `kami 0.1.0`, and `PySide6.QtWidgets` is not in `sys.modules` (run it in a subprocess for a clean import state)
- [ ] `test_unknown_command_errors`: `main(["frobnicate"])` exits with code 2 and a usage message
- [ ] `test_session_check_wayland_hotkey_fails`: monkeypatch `XDG_SESSION_TYPE=wayland`; the hotkey check is ✗ and mentions `kami toggle`
- [ ] `test_session_check_x11_without_pynput`: simulate `ImportError`; the result is ✗ with the pip hint
- [ ] `test_api_key_source_reported_not_value`: set `OPENROUTER_API_KEY=sk-secret123`; the rendered report contains `OPENROUTER_API_KEY` and not `secret123`
- [ ] `test_config_error_is_a_failed_check_not_a_crash`: bad TOML gives a ✗ config row, and the report still renders the other rows
- [ ] `test_config_warnings_listed`: warnings from Task 4 appear as ⚠ rows
- [ ] `test_endpoint_unreachable_is_failure`: `MockTransport` raises `ConnectError`, so the endpoint row is ✗ with Task 3's `network` message
- [ ] `test_model_not_listed_warns`: `/models` returns a list without the configured model, so the row is ⚠
- [ ] `test_doctor_never_posts_chat`: the `MockTransport` handler fails on any request to `/chat/completions`
- [ ] `test_exit_code_reflects_failures`: all ✓ gives 0; any ✗ gives 1

## Manual check

- [ ] Over SSH with no `DISPLAY`: `kami --version` and `kami doctor` both work
- [ ] On X11 and on Wayland, the report matches reality (hotkey, capture)

## Done when

- [ ] `kami --version` and `kami doctor` run without a display
- [ ] The key never appears in output
- [ ] Phase 1 exit criterion met: the report explains why the hotkey or capture won't work
- [ ] `/security-check` run on the diff

## Commits

1. `parse cli args before starting qt`
2. `add kami doctor health report`
