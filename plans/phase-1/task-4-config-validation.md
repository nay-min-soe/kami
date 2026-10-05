# Task 4 — Config validation

**Size:** S · **Depends on:** — · **Branch:** `config-validation`

## Goal

A broken `~/.config/kami/config.toml` gives a clear message that names the file,
the key and the fix. It never crashes Kami with a traceback.

## Current state

`load_config` in `src/kami/config.py`:

- Invalid TOML raises `tomllib.TOMLDecodeError` from `main()`, which crashes before the tray appears.
- Wrong types are accepted silently:
  - `allowed_apps = "firefox"` becomes `list("firefox")`, which is `["f","i","r",...]`.
    That is a quiet **safety bug**: the allowlist no longer means what the user wrote.
  - `model = 5` passes through, and `base_url = 5` crashes on `.rstrip`.
  - `[llm]` written as a string instead of a table crashes on `.get`.
- Unknown keys (typos like `allowed_app`) are ignored with no warning.

## Design

- New `ConfigError(ValueError)` in `config.py`, with a message like:
  `~/.config/kami/config.toml: [app_control] allowed_apps must be a list of app names, e.g. ["firefox"]`
- Small helpers that check types: `_table(data, "llm")`, `_str(table, "model", default)`,
  `_str_list(table, "allowed_apps")`.
- Unknown keys → collect them into `Config.warnings: list[str]` (not an error), so
  the panel or `kami doctor` can show "unknown key `allowed_app` — did you mean `allowed_apps`?"
  (`difflib.get_close_matches`).
- `base_url` must start with `http://` or `https://`.

## Files

| File | Change |
|---|---|
| `src/kami/config.py` | `ConfigError`, typed helpers, `warnings` field |
| `src/kami/app.py` | catch `ConfigError` in `main()`: print it, show a `QMessageBox.critical`, return exit code 2 |
| `tests/test_config.py` | new cases |
| `config.example.toml` | no key changes; make sure each key's comment states its type |

## Implementation

1. Wrap `tomllib.load` and raise `ConfigError` with the path plus the TOML parser's
   line and column (the parser's message already includes them).
2. Replace each `data.get(...)` with a typed helper. Keep today's defaults exactly
   so the existing tests stay green.
3. `allowed_apps`: must be a list of non-empty strings. Raise an error, don't coerce.
   This is the safety-relevant fix.
4. In `app.py`, load config **before** creating the overlay, and catch `ConfigError`.
   `QApplication` already exists at that point, so a message box works.
5. Show `config.warnings` once in the panel on startup (one line each). Skip this
   if it makes `overlay.py` messy; Task 7's `kami doctor` will print them too.

## Tests — add to `tests/test_config.py`

- [ ] `test_invalid_toml_raises_config_error_with_path`: write `[llm\n` and check the path is in the message
- [ ] `test_allowed_apps_string_is_rejected`: `allowed_apps = "firefox"` raises `ConfigError` (regression test for the safety bug)
- [ ] `test_allowed_apps_non_string_item_rejected`: `allowed_apps = ["firefox", 3]`
- [ ] `test_llm_section_must_be_table`: `llm = "x"`
- [ ] `test_model_must_be_string`: `model = 5`
- [ ] `test_base_url_must_be_http`: `base_url = "openrouter.ai"`
- [ ] `test_unknown_key_becomes_warning_with_suggestion`: `allowed_app = []` adds a warning that mentions `allowed_apps`
- [ ] `test_example_config_loads_cleanly`: `load_config(Path("config.example.toml"))` has no warnings (keeps the example honest)
- [ ] Existing 3 config tests still pass unchanged

## Manual check

- [ ] Break the TOML on purpose, run `kami`, and see a dialog naming the file and line, with no traceback

## Done when

- [ ] No config content can produce a traceback at startup
- [ ] A wrong-type `allowed_apps` is refused, never coerced
- [ ] `/security-check` run on the diff

## Commits

1. `validate config types and report clear errors`
2. `show config errors at startup`
