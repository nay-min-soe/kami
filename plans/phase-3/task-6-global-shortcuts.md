# Task 6 — Hotkey through `GlobalShortcuts`

**Size:** M · **Depends on:** Task 1, Task 2, Task 3 · **Branch:** `portal-hotkey` · **Owner:** both

## Goal

On Wayland desktops that have `org.freedesktop.portal.GlobalShortcuts` (KDE Plasma 6,
GNOME 48+, Hyprland), Kami registers its own hotkey, with no hand-made desktop shortcut,
when the optional `wayland` extra (`jeepney`) is installed. Everywhere else, `kami
toggle` stays the way to do it, and Kami's message names the exact fix: install the
extra, or add the desktop shortcut.

## Why

- `HotkeyListener.start()` returns early on Wayland with one generic line
  (`session.hotkey_fallback_message(session)`, from Task 2), and `kami doctor` marks the
  hotkey ✗ on every Wayland desktop, even where the fix is a normal desktop setting.
- **PySide6's QtDBus can't do this portal** (Task 1, Q13). It can neither send
  `BindShortcuts`' `a(sa{sv})` argument (a marshal error, the wrong type, or a libdbus
  abort) nor read one back. A failed call can leave the next one hanging. jeepney 0.9.0
  did all of it in the spike: the echo came back as `'oa(sa{sv})a{sv}'`, and
  `CreateSession`, `Response` and `Session.Close` worked against ScreenCast. So this task
  uses jeepney, as an optional extra (Plan change 1).
- This machine's GNOME 46 has no `GlobalShortcuts` and no `Registry` interface (Q8). Here
  the task changes only the messages. The portal path itself can only be tried on KDE or
  GNOME 48+.
- Config: `[hotkey] toggle = "<ctrl>+<alt>+k"` (`config.Config.hotkey`), in pynput
  syntax. The portal wants XDG shortcut syntax (`CTRL+ALT+k`).

## Design

### Where the code lives

jeepney is pure Python with no Qt, so the portal client is a **core** module,
`src/kami/portal_shortcuts.py` (backend-dev). It runs on its own daemon thread and
reports through two plain callbacks, the same way pynput does today.
`HotkeyListener` (frontend-dev) turns those callbacks into Qt signals, so they arrive on
the main thread (queued delivery, as with pynput's thread today). **Only that thread ever
touches the jeepney connection.** A portal session belongs to the connection that created
it (Task 1, Plan change 1 note), so every call for one session goes through it.

### Portal flow (on the client's thread)

1. Open a blocking session-bus connection (`jeepney.io.blocking.open_dbus_connection(
   bus="SESSION")`). Find the portal's **unique** name with `GetNameOwner(
   "org.freedesktop.portal.Desktop")`. jeepney's local `filter()` matches the sender's
   unique name, not the well-known name (Q13).
2. Read `GlobalShortcuts.version` with `Properties.Get` (2 s timeout). An error →
   `on_bound(BindReply("failed", reason="no-portal"))`, close, end.
3. `CreateSession({"handle_token": ("s", t1), "session_handle_token": ("s", t2)})`:
   1. `AddMatch` a `Response` rule (sender = the unique name, path =
      `portal.request_path(conn.unique_name, t1)`).
   2. Send the call, and wait in `conn.filter(rule)` with `recv_until_filtered(queue,
      timeout=...)`.
   3. On `TimeoutError`, send `Request.Close` on that path → `BindReply("timeout")`.

   The handle is `results["session_handle"]`, a `('s', str)` variant (Q8).
4. `BindShortcuts(session, [("toggle", {"description": ("s", "Show or hide Kami"),
   "preferred_trigger": ("s", <trigger>)})], "", {"handle_token": ("s", t3)})`, with
   signature `oa(sa{sv})sa{sv}` and the same `Response` wait (60 s,
   `portal.BIND_TIMEOUT_MS`). The desktop shows its own dialog, where you can accept or
   pick other keys.
5. The `Response`'s `results` go through `portal.unwrap_vardict` (jeepney gives every
   variant as a `(signature, value)` pair), then `portal.parse_bind_reply`. That picks the
   `trigger_description` of `toggle`, i.e. the keys the desktop really chose →
   `on_bound(reply)`.
6. `AddMatch` an `Activated` rule (sender = the unique name, interface
   `org.freedesktop.portal.GlobalShortcuts`, path `/org/freedesktop/portal/desktop`).
   Loop on `recv_until_filtered(queue, timeout=0.5)`. For each signal where
   `portal.is_our_activation(body[0], body[1], session)` is true, call `on_activated()`.
   After each wait, check the stop flag.
7. **Stop** (`close()` from the main thread sets the flag; the thread does the rest):
   send `org.freedesktop.portal.Session.Close` on the session handle with
   `send_and_get_reply(..., timeout=1)` (a `TimeoutError` is ignored), then
   `conn.close()`. If that doesn't get through, nothing is lost: the portal closes a
   session when its connection goes away. `close()` joins the thread for at most 1.5 s.

Start-up never waits on the bus: `start()` only starts the thread. The desktop remembers
the binding, so the dialog should only appear the first time (KDE: needs you).

### Without the extra

`portal_shortcuts.available()` is `False` when `jeepney` can't be imported. Then
`HotkeyListener` reads the portal versions once with `doctor.read_portal_versions()` (Q12:
QtDBus, no `QCoreApplication` needed, 2.4 ms for three reads), and picks the reason:

- `GlobalShortcuts` present → `no-jeepney` (*"…needs the wayland extra"*)
- missing → `no-portal`

### App id (Plan change 5)

xdg-desktop-portal takes an unsandboxed app's id from its **systemd scope**, not from the
app (Q2: the screenshot grant was filed under `com.microsoft.VSCode`). There's no
`Registry` on 1.18.4 (Q8). So KDE will probably list Kami's shortcut under whatever
launched it (Konsole, the IDE, the autostart entry). If you start Kami another way, it may
ask again.

This task builds the flow **without** registering. Task 7 ships `org.kami.Kami.desktop`
and documents starting Kami in an `app-org.kami.Kami-<n>.scope`, which gives one stable
id. Whether KDE needs `Registry.Register` on newer portals is the KDE `shortcut.py
--register` check (needs you). If it does, that's a Plan change, not a quiet addition here.

### Async status

`start()` returns *"Asking the desktop for the hotkey…"* on the portal path. The new
signal `HotkeyListener.status_changed(str)` delivers the final line (bound, or the
fallback), and `app.py` updates the tray tooltip and logs it. The pynput path still
returns its final line at once and never emits `status_changed`.

### Fallback text

`session.hotkey_fallback_message(session, reason="no-portal")` = a reason prefix + the
fix for that desktop:

| reason | prefix |
|---|---|
| `no-portal` | *(none)* |
| `no-jeepney` | *"Kami's own Wayland hotkey needs the wayland extra: pip install 'kami[wayland]'. Until then: "* |
| `refused` | *"The desktop didn't register Kami's hotkey. "* |
| `timeout` | *"The desktop didn't answer about the hotkey. "* |

| desktop | fix |
|---|---|
| gnome | *"GNOME 46 and older can't give apps a global hotkey. Add one in Settings → Keyboard → View and Customize Shortcuts → Custom Shortcuts that runs `kami toggle`."* |
| kde | *"Add one in System Settings → Keyboard → Shortcuts → Add New → Command or Script, running `kami toggle`."* |
| sway | *"Add `bindsym Ctrl+Alt+k exec kami toggle` to your Sway config."* |
| hyprland | *"Add `bind = CTRL ALT, K, exec, kami toggle` to hyprland.conf."* |
| other | *"Bind a desktop shortcut that runs `kami toggle`."* |

`bad-combo` uses the `ValueError` message followed by the desktop fix. Called with one
argument, it gives the `no-portal` text. Task 2's test
`test_hotkey_fallback_message_wayland_keeps_old_text` is updated to the new GNOME / other
texts in this task (named in Tests).

### `kami doctor`

`check_hotkey(env, combo, portals=None, has_jeepney=None)`. On Wayland:

| `GlobalShortcuts` | jeepney | Row |
|---|---|---|
| version N | yes | `✓ GlobalShortcuts portal vN · your desktop asks once` |
| version N | no | `⚠ GlobalShortcuts portal vN, but Kami needs the wayland extra → pip install 'kami[wayland]'` |
| missing or not checked | — | `⚠ <hotkey_fallback_message(session, "no-portal")>` |

Wayland without the portal is ⚠, not ✗, because it has a normal fix. X11 rows are
unchanged. `has_jeepney=None` means `portal_shortcuts.available()`.

`doctor.read_portal_versions()` is the one QtDBus reader outside `ui/portal.py` (README
Layers rule). It imports Qt inside the function, like `check_running`, and needs no
`QCoreApplication` (Q12).

**This task owns reading the versions in `collect`**, including when the reader crashes.
Task 7 only passes the same result on to the screen-grab row:

```python
versions = None
if portals is not None:
    try:
        versions = dict(portals())
    except Exception:  # a broken D-Bus must not stop the report
        versions = {"Screenshot": None, "GlobalShortcuts": None}
```

### Known limits

- If you change the shortcut in the desktop's settings while Kami runs, the tooltip
  shows the old keys until a restart. `ShortcutsChanged` isn't handled.
- Never on X11: the pynput path stays as it is.

## Contract

backend-dev builds this; frontend-dev calls it.

```python
# src/kami/session.py  (add / change)
def portal_trigger(combo: str) -> str: ...
    # "<ctrl>+<alt>+k" -> "CTRL+ALT+k"; raises ValueError("<plain words>") for unknown keys
def hotkey_fallback_message(session: Session, reason: str = "no-portal") -> str: ...
    # reason: "no-portal" | "no-jeepney" | "refused" | "timeout"

# src/kami/portal.py  (add)
SHORTCUT_ID = "toggle"
SHORTCUT_DESCRIPTION = "Show or hide Kami"
BIND_TIMEOUT_MS = 60_000

@dataclass(frozen=True)
class BindReply:
    status: str        # "ok" | "cancelled" | "failed" | "timeout"
    trigger: str = ""  # trigger_description the desktop chose for SHORTCUT_ID, "" if none given
    reason: str = ""   # safe to log: "no-portal", "no session", "dbus error", "response=2", "timeout"

def unwrap_vardict(value: object) -> dict: ...
    # jeepney a{sv} -> plain dict: each ("sig", v) pair becomes v; "a{sv}" values recurse;
    # "a(sa{sv})" values become [(str, dict), ...]; anything that isn't a (str, value)
    # pair is dropped. Not a dict -> {}.
def parse_session_reply(code: object, results: Mapping[str, object]) -> str | None: ...
    # session_handle (non-empty str) on code 0, else None
def parse_bind_reply(code: object, results: Mapping[str, object]) -> BindReply: ...
    # results["shortcuts"] as list[tuple[str, dict]] (after unwrap_vardict)
def is_our_activation(session_handle: object, shortcut_id: object, ours: str) -> bool: ...

# src/kami/portal_shortcuts.py  (new, core: no Qt; needs the optional `wayland` extra)
def available() -> bool: ...            # jeepney can be imported
def bind_body(session: str, trigger: str, token: str) -> tuple: ...
    # the BindShortcuts body in jeepney's variant form, signature "oa(sa{sv})sa{sv}"
class GlobalShortcuts:
    def __init__(self, trigger: str,
                 on_bound: Callable[[BindReply], None],
                 on_activated: Callable[[], None],
                 *, timeout_s: float = BIND_TIMEOUT_MS / 1000,
                 connect: Callable[[], object] | None = None) -> None: ...
        # connect: returns a jeepney blocking connection (tests pass a fake)
    def start(self) -> None: ...        # starts the "kami-shortcuts" daemon thread; returns at once
    def close(self, wait_s: float = 1.5) -> None: ...
        # thread sends Session.Close (1 s), closes the connection; safe twice or before start
    # on_bound: exactly once per start(), on the client's thread
    # on_activated: on the client's thread, once per matching Activated signal

# src/kami/doctor.py  (add / change)
def read_portal_versions() -> dict[str, int | None]: ...   # {"Screenshot": 2, "GlobalShortcuts": None}
def check_hotkey(env, combo: str, portals: Mapping[str, int | None] | None = None,
                 has_jeepney: bool | None = None) -> Check: ...
def collect(env=None, config_path=None, http=None, running=True,
            portals: Callable[[], Mapping[str, int | None]] | None = None) -> list[Check]: ...
    # portals=None -> versions not checked; run_doctor() passes read_portal_versions
```

Frontend side (`src/kami/hotkey.py`):

```python
class HotkeyListener(QObject):
    triggered = Signal()          # unchanged
    status_changed = Signal(str)  # new: the final hotkey line, portal path only
    _bound = Signal(object)       # internal: carries BindReply from the client's thread
    def start(self) -> str: ...   # unchanged type
    def stop(self) -> None: ...   # also closes the portal client
```

## Backend part (backend-dev)

| File | Change |
|---|---|
| `pyproject.toml` | new optional extra `wayland = ["jeepney>=0.9"]` (comment: "global hotkey on Wayland through the GlobalShortcuts portal") |
| `.github/workflows/ci.yml` | install `".[dev,wayland]"`, so the jeepney tests run in CI |
| `src/kami/session.py` | `portal_trigger`; `hotkey_fallback_message(session, reason)` with the desktop texts |
| `src/kami/portal.py` | `SHORTCUT_ID`, `SHORTCUT_DESCRIPTION`, `BIND_TIMEOUT_MS`, `BindReply`, `unwrap_vardict`, `parse_session_reply`, `parse_bind_reply`, `is_our_activation` |
| `src/kami/portal_shortcuts.py` | new: the jeepney client (Design steps 1–7) |
| `src/kami/doctor.py` | `read_portal_versions`; `check_hotkey(env, combo, portals, has_jeepney)`; `collect(..., portals=None)` with the try / except above; `run_doctor` passes `read_portal_versions` |
| `tests/test_session.py` | `portal_trigger` and fallback message cases; update the Task 2 fallback test |
| `tests/test_portal.py` | unwrap, session / bind reply parsing, activation filter |
| `tests/test_portal_shortcuts.py` | new: `bind_body`, and the thread with a fake connection |
| `tests/test_doctor.py` | Wayland rows; reader crash; rename `test_session_check_wayland_hotkey_fails` |
| `config.example.toml` | comment on `[hotkey] toggle`: on Wayland these are the *preferred* keys, and the desktop has the last word; the portal needs `pip install 'kami[wayland]'` |
| `ARCHITECTURE.md` | `portal_shortcuts.py` box in Core; **Libraries** row for jeepney (optional) |

Steps:

1. Install the extra in the dev venv: `.venv-1/bin/pip install -e '.[wayland]'`. Check
   that `.venv-1/bin/python -c "import jeepney; print(jeepney.__version__)"` prints
   0.9.x.
2. **`portal_trigger`**:
   1. Split on `+`, then trim and lowercase each token.
   2. Modifiers: `<ctrl>`, `<ctrl_l>`, `<ctrl_r>` → `CTRL`; `<alt>`, `<alt_l>`, `<alt_r>` →
      `ALT`; `<shift>`, `<shift_l>`, `<shift_r>` → `SHIFT`; `<cmd>`, `<cmd_l>`, `<cmd_r>`,
      `<super>` → `LOGO`.
   3. Exactly one key, the last token: a single letter or digit → that character,
      lowercase; `<f1>`–`<f12>` → `F1`–`F12`; `<space>` → `space`; `<enter>` → `Return`;
      `<tab>` → `Tab`; `<esc>` → `Escape`.
   4. Output the modifiers in the order `CTRL+ALT+SHIFT+LOGO`, then the key.
   5. `ValueError` cases: no key, two keys, an unknown token, or no modifier among `CTRL`
      / `ALT` / `LOGO`. The message names the token and lists what works, for example
      *"Kami can't turn `<alt_gr>` into a desktop shortcut. Use ctrl, alt, shift or super
      with a letter, digit, F1–F12, space, enter, tab or esc."*
3. **`hotkey_fallback_message(session, reason)`**: the two tables in Design.
   `HOTKEY_FALLBACK_WAYLAND` / `HOTKEY_FALLBACK_OTHER` are replaced by the desktop texts.
   The X11 / pynput messages in `hotkey.py` and `doctor.py` don't change.
4. **`portal.py`**:
   - `unwrap_vardict` per the Contract.
   - `parse_session_reply`: code 0 and a non-empty `str` `session_handle` → that string;
     anything else → `None`.
   - `parse_bind_reply`:
     - code 0 → `ok`, with `trigger` taken from the `shortcuts` entry whose id is
       `SHORTCUT_ID`. Use it only if it's a `str`, keep printable characters only, and
       cap it at 60. Skip entries that aren't 2-tuples of `(str, dict)`.
     - Code 1 → `cancelled`.
     - Anything else → `failed`, `response=<code>`.
   - `is_our_activation`: both arguments are `str`, `session_handle == ours`, and
     `shortcut_id == SHORTCUT_ID`.
5. **`portal_shortcuts.py`**:
   - `available()`: `try: import jeepney` → `True`; `except ImportError` → `False`. A
     plain import, so `sys.modules["jeepney"] = None` (builder check 3) counts as missing.
   - `bind_body`: builds the tuple in Design step 4.
   - `GlobalShortcuts`:
     - Import jeepney inside the thread function, so the module imports without it.
     - Follow Design steps 1–7, reusing `portal.new_token()` and `portal.request_path()`.
       `spike/shortcut.py` has working jeepney calls for every step (`MatchRule`,
       `message_bus.AddMatch` through a `Proxy`, `conn.filter`, `recv_until_filtered`,
       `Session.Close`). Copy those patterns, not its prints.
     - Any exception on the thread → `on_bound(BindReply("failed", reason="dbus error"))`
       if `on_bound` hasn't been called yet. Then close the connection. Log the type name
       only.
     - Log `hotkey portal step=<create|bind|listen> ms=N`. Never the trigger text or the
       handle.
6. **`doctor.read_portal_versions()`**:
   1. Import `PySide6.QtDBus` inside the function.
   2. For `Screenshot` and `GlobalShortcuts`, call `Properties.Get` with
      `QDBusMessage.createMethodCall` + `sessionBus().call(msg, QDBus.CallMode.Block,
      2000)` (the pattern in `spike/portal_versions.py`). Unwrap the `QDBusVariant`.
      Anything else gives `None`.
   3. If Qt can't load at all, return both as `None`.
7. **`collect`**: read the versions with the try / except in Design. Pass them, and
   `has_jeepney`, to `check_hotkey` through `guarded`, as today. **`check_hotkey`**:
   Wayland follows the Design table; otherwise it's today's code.
8. `.venv-1/bin/python -m pytest -q` and `.venv-1/bin/ruff check .`.

## Frontend part (frontend-dev)

| File | Change |
|---|---|
| `src/kami/hotkey.py` | `status_changed` and `_bound` signals; `start()` picks pynput / portal / fallback; `stop()` closes the portal client |
| `src/kami/app.py` | connect `hotkey.status_changed` to the tray tooltip and the log |
| `README.md` | rewrite "Hotkey: X11 vs Wayland": the `wayland` extra, the desktop's dialog, the per-desktop fallback |

Steps:

1. **`HotkeyListener.start()`**:
   - `self.session.hotkey == "pynput"`: today's code, unchanged.
   - `"portal"`:
     1. Convert with `portal_trigger(self.combo)`. On `ValueError`, log `hotkey
        method=desktop-shortcut reason=bad-combo` and return the error text plus
        `hotkey_fallback_message(self.session)`.
     2. If `not portal_shortcuts.available()`: `versions = read_portal_versions()`;
        `reason = "no-jeepney" if versions.get("GlobalShortcuts") else "no-portal"`. Log
        `hotkey method=desktop-shortcut reason=<reason>` and return
        `hotkey_fallback_message(self.session, reason)`.
     3. Otherwise connect `self._bound` → `self._on_bound` (queued, main thread), and
        create `self._client = GlobalShortcuts(trigger, on_bound=self._bound.emit,
        on_activated=self.triggered.emit)`.
     4. Call `self._client.start()`, and return *"Asking the desktop for the hotkey…"*.
2. **`_on_bound(reply)`** (main thread):
   - `ok`: emit `status_changed(f"Hotkey {reply.trigger or trigger} (set by your
     desktop)")`, and log `hotkey method=portal bound=yes`.
   - `failed` with reason `no-portal`: `hotkey_fallback_message(self.session,
     "no-portal")`.
   - `timeout`: `hotkey_fallback_message(self.session, "timeout")`.
   - other `cancelled` / `failed`: `hotkey_fallback_message(self.session, "refused")`.
   - Every case except `ok` emits that text through `status_changed` and logs `hotkey
     method=desktop-shortcut reason=<reply.reason or reply.status>`.
3. **`HotkeyListener.stop()`**: stop pynput if it's running, and `self._client.close()` if
   there is one.
4. **`app.py`**:
   1. Add a small nested function `on_hotkey_status(text)` that calls
      `tray.setToolTip(f"Kami: {text}")` and `log.info("hotkey: %s", text)`.
   2. Connect `hotkey.status_changed` to it right after `tray.setToolTip(...)`. The portal
      answer can't arrive before the event loop runs, so nothing is lost.
   3. The printed start line keeps using `status`.
5. `.venv-1/bin/python -m pytest -q` and `.venv-1/bin/ruff check .`.

## Tests

- [ ] `test_portal_trigger_ctrl_alt_k` in `tests/test_session.py` (`<ctrl>+<alt>+k` → `CTRL+ALT+k`)
- [ ] `test_portal_trigger_super_and_order` (`<shift>+<cmd>+<ctrl>+a` → `CTRL+SHIFT+LOGO+a`)
- [ ] `test_portal_trigger_function_and_named_keys` (`<f5>`, `<space>`, `<enter>`, `<esc>`)
- [ ] `test_portal_trigger_unknown_key_message` (names the token)
- [ ] `test_portal_trigger_needs_a_modifier` (`k` alone, `<shift>+k`)
- [ ] `test_portal_trigger_rejects_two_keys`
- [ ] `test_hotkey_fallback_names_the_desktop` (gnome menu path, kde, sway, hyprland, other)
- [ ] `test_hotkey_fallback_reason_prefix` (no-jeepney names `kami[wayland]`, refused, timeout)
- [ ] `test_hotkey_fallback_message_wayland_keeps_old_text` → renamed `test_hotkey_fallback_default_is_no_portal_text`
- [ ] `test_unwrap_vardict_plain_and_nested` in `tests/test_portal.py` (`{"session_handle": ("s", "/x")}`, an `a(sa{sv})` value, a non-pair value dropped, a non-dict → `{}`)
- [ ] `test_parse_session_reply_ok_and_errors` (missing, empty or non-`str` handle → `None`)
- [ ] `test_parse_bind_reply_picks_our_trigger` (other ids ignored; malformed entries skipped; non-`str` and over-long triggers dropped or capped)
- [ ] `test_parse_bind_reply_cancelled_and_failed`
- [ ] `test_is_our_activation_filters_session_and_id` (non-`str` arguments → `False`)
- [ ] `test_bind_body_shape` in `tests/test_portal_shortcuts.py` (no jeepney needed: `("toggle", {"description": ("s", …), "preferred_trigger": ("s", "CTRL+ALT+k")})`)
- [ ] `test_available_without_jeepney` (`monkeypatch.setitem(sys.modules, "jeepney", None)` → `False`; the module still imports)
- [ ] `test_client_binds_and_reports_activation` (`pytest.importorskip("jeepney")`; a fake connection answers `GetNameOwner`, `version`, both `Response`s, then one `Activated` for our session and one for another; `on_bound` gets `ok` + trigger once, and `on_activated` fires exactly once)
- [ ] `test_client_no_portal` (fake: `Properties.Get` returns an error → `on_bound` gets `failed` / `no-portal`; no `CreateSession` sent)
- [ ] `test_client_timeout_closes_request` (fake never answers `BindShortcuts` → `Request.Close` sent on the request path, `on_bound` gets `timeout`)
- [ ] `test_client_close_sends_session_close` (`close()` → `Session.Close` on the handle, connection closed, the thread ends within 1.5 s; a second `close()` does nothing)
- [ ] `test_doctor_hotkey_wayland_no_portal_warns_with_fix` in `tests/test_doctor.py` (GNOME text, `warn`)
- [ ] `test_doctor_hotkey_wayland_with_portal` (`{"GlobalShortcuts": 1}`, `has_jeepney=True` → `ok`, mentions v1)
- [ ] `test_doctor_hotkey_portal_without_jeepney` (`has_jeepney=False` → `warn`, names `kami[wayland]`)
- [ ] `test_doctor_portals_not_checked_by_default` (`collect` without `portals` never touches D-Bus)
- [ ] `test_doctor_portal_reader_crash_is_not_fatal` (`portals` raises → every row still renders; hotkey shows the no-portal fallback)
- [ ] `test_session_check_wayland_hotkey_fails` → renamed `test_session_check_wayland_hotkey_warns`, asserting `warn` and `kami toggle`

## Manual check

**Builder checks: no window on the real display, no portal call** (GNOME 46 has no
`GlobalShortcuts`, so there's nothing to call).

1. [ ] `.venv-1/bin/python -m kami doctor` shows
   `Hotkey ⚠ GNOME 46 and older can't give apps a global hotkey. Add one in Settings → …`.
2. [ ] Doctor's `Running` row says "not running". Then run
   `QT_QPA_PLATFORM=offscreen timeout 20 .venv-1/bin/python -m kami; grep "hotkey method" ~/.local/state/kami/kami.log | tail -1`.
   It shows `method=desktop-shortcut reason=no-portal`, with jeepney installed (the
   client's own version check). The start line and the `hotkey:` line are less than 3 s
   apart.
3. [ ] The same with jeepney hidden:
   `QT_QPA_PLATFORM=offscreen timeout 20 .venv-1/bin/python -c "import sys; sys.modules['jeepney'] = None; from kami.cli import main; main([])"`.
   Also `reason=no-portal` (from `read_portal_versions`).

Yours (in `your-checklist.md`):

- [ ] KDE Wayland VM, with `pip install 'kami[wayland]'`: the first start shows KDE's
      shortcut dialog. Accept, then press the keys: the panel toggles, and the tray
      tooltip shows the keys. Restart Kami: no dialog, and the keys still work
- [ ] KDE: in System Settings → Shortcuts, note which app the binding is listed under
      (Task 1, Q8). Start Kami as `org.kami.Kami` (Task 7's instructions) and look again
- [ ] KDE: click **Cancel** in the dialog: the tooltip shows the KDE "didn't register"
      text
- [ ] KDE without the extra: doctor says `… needs the wayland extra → pip install
      'kami[wayland]'`
- [ ] GNOME 46: your existing custom shortcut to `kami toggle` still works
- [ ] Optional, GNOME 48+ VM: the same as KDE
- [ ] X11: the pynput hotkey is unchanged

## Security

Run `/security-check`. The task adds a dependency (an optional extra, with a
minimum-version pin), talks to the session bus, and acts on a signal from it. Check:

- `Activated` is accepted only from the portal's unique name, and only for our session
  handle and shortcut id.
- The trigger text from the desktop is type-checked, stripped to printable characters
  and capped before it reaches the tooltip.
- Only the client's thread touches the jeepney connection.
- Logs hold the method, step, reason and times only.
- `close()` can't hang quit for more than 1.5 s.

## Done when

- [ ] All tests above pass with the earlier ones (CI installs `.[dev,wayland]`), and ruff
      is clean
- [ ] `pyproject.toml` has `wayland = ["jeepney>=0.9"]`, and the base install still has
      only PySide6 and httpx
- [ ] On this GNOME 46, the log says `reason=no-portal` with and without jeepney, and
      doctor shows the GNOME fix as ⚠
- [ ] No D-Bus call blocks the main thread before `app.exec()`: the client runs on its
      own thread. The only main-thread read is `read_portal_versions` without jeepney
      (milliseconds, Q12)
- [ ] The pynput path in `hotkey.py` is unchanged (`git diff` shows only the new branch)
- [ ] Builder checks 1–3 passed with no window on the real display
- [ ] Your hand check: on KDE Wayland, with the extra, the hotkey works with no hand-made
      shortcut

## Commits

1. `convert hotkey to portal shortcut syntax`
2. `name the desktop fix when there's no hotkey portal`
3. `add the wayland extra and a global shortcuts portal client`
4. `report the shortcuts portal in doctor`
5. `use the shortcuts portal on wayland when available`
