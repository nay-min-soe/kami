# Task 6 — Tests for app control and meetings

**Size:** S · **Depends on:** — · **Branch:** `tests-app-control-meetings`

## Goal

Cover the two modules that have no tests today, especially the path where
app control actually runs a process.

`LLMClient` tests are part of [Task 3](task-3-llm-errors.md), since they need the
injected HTTP client added there.

## Current state

- `modes/app_control.run()` has no tests. It is the only code that starts processes.
- `modes/meetings.py` has no tests.
- Both modules are pure Python, so they can be tested without Qt.

## Files

| File | Change |
|---|---|
| `tests/test_app_control.py` | new |
| `tests/test_meetings.py` | new |
| `tests/conftest.py` | new: `FakeLLM` that records prompts and returns canned text |

No source changes are expected. If a test shows a bug, fix it in a separate commit
with the test that proves it.

## Implementation notes

- **Never start a real process in tests.** Use `monkeypatch` to replace
  `app_control.subprocess.Popen` with a recorder, and `app_control.shutil.which`
  with a fake that returns `/usr/bin/<name>` or `None`.
- `FakeLLM` needs only `ask(prompt, system=None)` and `ask_about_image(png, prompt, system=None)`.
  It records the arguments and returns a preset string.

## Tests — `tests/test_app_control.py`

- [ ] `test_unknown_kind_returns_message_and_never_asks`: `run("delete", ...)` returns "doesn't know how", and confirm is never called
- [ ] `test_not_allowed_app_raises_and_never_launches`: `NotAllowed` is raised, and `Popen` is not called
- [ ] `test_refused_confirm_launches_nothing`: confirm returns False, the result is "Cancelled...", and `Popen` is not called
- [ ] `test_confirmed_launch_runs_resolved_path`: `Popen` is called once with `["/usr/bin/firefox"]` and `start_new_session=True`
- [ ] `test_launch_missing_binary`: `which` returns `None`, the result is "Could not find", and `Popen` is not called
- [ ] `test_launch_passes_no_shell`: assert that `shell` is not in the `Popen` kwargs, so app names can't inject shell commands
- [ ] `test_every_handler_kind_goes_through_gate`: loop over `HANDLERS` with a denying confirm; no handler runs. This guards future action kinds.

## Tests — `tests/test_meetings.py`

- [ ] `test_summarize_puts_transcript_in_prompt`: `FakeLLM` receives a prompt that contains the transcript and the "action items" heading
- [ ] `test_summarize_returns_model_text`: the return value is the fake's reply
- [ ] `test_transcript_with_braces_is_safe`: a transcript containing `{x}` doesn't break `str.format` (it shouldn't, because `format` doesn't re-parse inserted values, but pin it)
- [ ] `test_start_capture_not_implemented`: raises `NotImplementedError` (remove this test in Phase 4)

## Done when

- [ ] All new tests pass in CI with no display and no network
- [ ] `pytest` total goes from 10 to about 21 tests
- [ ] No test can start a real process

## Commits

1. `add app control tests`
2. `add meetings tests`
