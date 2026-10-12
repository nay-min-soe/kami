# Task 1 — Wayland spike: measure what works

**Size:** S · **Depends on:** — · **Branch:** `wayland-spike` · **Owner:** frontend · **Status:** ✅ done (scripts `0bd5417`; findings below; the "needs you" rows are in `your-checklist.md`)

## Goal

The open Wayland questions are answered with small scripts, and the answers are written
into this file before anything is built, so Tasks 3–6 don't rest on guesses. The scripts
stay in the repo, so you can rerun the same checks on KDE. This is the Phase 3 version of
Phase 2's "measure first, then fix".

## Why

Today, for each question below, the plan has only a guess:

- `_capture_region` (`ui/overlay.py:328`) calls `screen.grabWindow(0, …)`. On Wayland
  this returns an empty pixmap, and the panel shows `CAPTURE_FAILED`. Nobody has called
  the Screenshot portal from Kami's Python yet.
- `RegionSelector.start()` and `summon()` find "the screen under the cursor" with
  `QCursor.pos()`. On Wayland, Qt only knows the cursor position while it is over one of
  Kami's own windows.
- `RegionSelector.mouseReleaseEvent` emits `r.translated(self.geometry().topLeft())`.
  On Wayland a client doesn't know where its window is, so that offset may be wrong.
- `AnnotationLayer` positions a small frameless window with `setGeometry()`. Wayland
  ignores client-set positions, and GNOME has no `wlr-layer-shell`.
- `_on_region` waits 150 ms for the selector to disappear. Nobody knows whether that is
  enough for a portal screenshot on GNOME, where the compositor animates windows.
- Kami has no `.desktop` file or app id. Nobody knows whether KDE's `GlobalShortcuts`
  accepts an app without one.

## Design

### What runs where

All scripts run on this machine (GNOME 46 Wayland, one 1920×1080 screen at 100 %) with:

```bash
.venv-1/bin/python -I plans/phase-3/spike/<script>.py [--timeout 20]
```

On the KDE VM there is no `.venv-1`. There, the same scripts run with
`uv run --no-project --with PySide6 python -I plans/phase-3/spike/<script>.py`. The scripts import nothing
from `kami`, so they need only PySide6.

Each script answers its questions without a click, drag or key press: it reads pixels from
the portal's own screenshot instead of looking at the screen. Anything that needs a hand
(clicking a dialog or the desktop picker, a second monitor, KDE, X11) is written in the
Findings as **"needs you"**, and the exact command goes in [How to rerun](#how-to-rerun).

### Live portal calls (the dialog rule)

- Every portal call has a timeout (`--timeout`, default 20 s). On timeout the script calls
  `org.freedesktop.portal.Request.Close` on the request path, which closes any dialog
  the portal opened. It then prints `TIMEOUT (a dialog probably appeared)` and exits
  with code 3.
- One attempt per question per run. **Don't retry in a loop.** If Q2's first call times
  out, every portal-based row (Q3, Q4, Q5, Q10) becomes "needs you: click Allow once, then
  rerun". The non-portal rows (Q6, Q7, Q8, Q9, Q12, Q13) still get answered.
- Before the first call and after the last one, read the permission store, so a stored
  grant shows up even if no dialog appeared:

  ```bash
  gdbus call --session --dest org.freedesktop.impl.portal.PermissionStore \
    --object-path /org/freedesktop/impl/portal/PermissionStore \
    --method org.freedesktop.impl.portal.PermissionStore.List screenshot
  ```

  (On 2026-10-12 this printed `(@as [],)`: nothing granted yet.)

### Trusting the reply, and deleting the file

The scripts delete a file whose name came over D-Bus, so they use the same guards Kami
will use (Task 3's `portal.load_screenshot`):

- **Only the portal's reply counts.** `Response` is connected with the service name
  `org.freedesktop.portal.Desktop`, on the request path the script predicted. A signal
  from any other sender, or on any other path, is ignored.
- **Delete only a checked regular file.** Before reading or deleting, the URI must pass
  four checks:
  1. the scheme is `file`
  2. the host is empty or `localhost`
  3. the percent-decoded path is absolute
  4. `os.lstat` shows a regular file (not a symlink, FIFO or directory)

  Then: `os.open(path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK)`, `os.fstat(fd)` to check
  again that it's a regular file, read at most 64 MB + 1 byte, close, and `os.unlink`.
  If any check fails, the script prints `not deleted (<reason>)` and leaves the file
  alone. The reason is a word or two, never the path.

### Privacy in the scripts

- A script never saves an image. It reads the portal's PNG into memory and deletes that
  exact file at once (Q3 records whether that worked). It prints only sizes, timings,
  counts and RGB averages over small test areas.
- The URI's **directory** may be written into the Findings (for example
  `~/Pictures/Screenshots/`), never a full file name with a timestamp. Don't commit
  screenshots or anything that shows the desktop.

### Questions to answer

| # | Question | Script | Who |
|---|---|---|---|
| Q1 | Can `PySide6.QtDBus` call `Screenshot` and receive `Request.Response`? Which way of connecting works: a slot with signature `(uint, "QVariantMap")`, or a slot taking a `QDBusMessage` that reads `message.arguments()`? Subscribing **before** the call, using the request path built from `handle_token` and the bus's unique name (`:1.42` → `/org/freedesktop/portal/desktop/request/1_42/<token>`)? Which keys come back in `results`, and as which Python types? | `portal_shot.py` | builder |
| Q2 | With `interactive: false`, does GNOME 46 show a permission dialog to an unsandboxed app? First time only, or every time? What `response` code does **Deny** give (1 or 2)? | `portal_shot.py` ×3 + permission store | builder (timeout = dialog); Deny code: needs you |
| Q3 | Where does the portal write the PNG (`/tmp`, `~/Pictures/…`, `$XDG_RUNTIME_DIR`, a `/run/user/…/doc/` path)? Is it a regular file? Can Kami delete it? Does anything else keep a copy (a notification with a thumbnail, the clipboard)? | `portal_shot.py` | builder (path, delete); notification / clipboard: needs you |
| Q4 | What does a non-interactive shot contain? Compare the image size with `QScreen.geometry()` × `devicePixelRatio()`. With two monitors or a 125 % / 200 % scale: one stitched image or one screen? At which pixel scale? | `portal_shot.py --layout` | builder: 1 screen at 100 %; needs you: 2 screens, 125 %, 200 % |
| Q5 | Does a full-screen, transparent, `WindowTransparentForInput`, `WA_ShowWithoutActivating` window (`setScreen(s)` + `showFullScreen()`) show **above** other windows on GNOME, without taking focus? Does it let clicks through? | `layer_probe.py` (draws a magenta 200×200 square at (100, 100); a portal shot checks the pixels; `isActiveWindow()` checks focus) | builder: visible + focus; clicks: needs you |
| Q6 | Does `QWidget.setScreen(s)` followed by `showFullScreen()` open the window on screen `s`? What do `geometry()`, `screen()`, `isVisible()` and `windowHandle()` report (a) straight after `showFullScreen()`, (b) at the first `exposeEvent` / `showEvent`, (c) after a 100 ms single-shot? Are `geometry()` and `screen().geometry()` equal (that matters for `RegionSelector`'s offset)? | `layer_probe.py` | builder: 1 screen; needs you: 2 screens |
| Q7 | When Kami is summoned by `kami toggle` (cursor not over a Kami window), what do `QCursor.pos()` and the shown window's `screen()` report? | `where_am_i.py` | builder: 1 screen; needs you: 2 screens |
| Q8 | Do GNOME 46, KDE Plasma 6 and GNOME 48+ expose `GlobalShortcuts`? Which version? Does `BindShortcuts` show a dialog? Kami has no app id: does `BindShortcuts` work without calling `org.freedesktop.host.portal.Registry.Register`? Under which app name does KDE's System Settings → Shortcuts list the binding (Kami, python3, Konsole, or none)? | `portal_versions.py`; KDE: `shortcut.py` | builder: GNOME 46; needs you: KDE, GNOME 48 |
| Q9 | Run with `QT_QPA_PLATFORM=xcb` (XWayland) on a Wayland session: is `grabWindow(0, …)` empty, all black, or only Kami's own windows? | `xwayland_grab.py` | builder |
| Q10 | After a full-screen Kami window is hidden, how many ms until it's gone from a portal screenshot? (Hide the magenta window, then take shots after 0, 150, 300 and 600 ms. Each run checks one delay.) | `layer_probe.py --hide-delay N` | builder |
| Q11 | With `interactive: true` (the desktop's picker), is the returned image already cropped to the picked area? Same URI rules as Q3? | `portal_shot.py --interactive --timeout 120` | needs you (only you can click the picker) |
| Q12 | Can `kami doctor` read a portal's `version` property with QtDBus when there is no running `QCoreApplication`? Or does it have to create one first? How long does the call take? | `portal_versions.py --no-app` | builder |
| Q13 | Can PySide6 QtDBus **send** an `a(sa{sv})` argument (what `BindShortcuts` takes) and **read** one back (what its `Response` and `ShortcutsChanged` carry)? How does an **object path** (`o`) arrive: as a bare argument (like `Activated`'s `session_handle`) and as a value inside `a{sv}` (some portals send `session_handle` that way)? GNOME 46 has no `GlobalShortcuts`, so test on our own object: register a tiny service on the session bus (`org.kami.Spike`) whose method takes and returns `(o, a(sa{sv}), a{sv})`. Call it with `/org/kami/test`, `[("toggle", {"description": "Show or hide Kami", "preferred_trigger": "CTRL+ALT+k"})]`, and `{"session_handle": <object path>}`. Check the wire signature, and print the Python type of every part of the reply (`QDBusObjectPath`? `QDBusArgument`? `QDBusVariant`?) | `marshal_check.py` | builder |

Q1 is a go / no-go for `QtDBus`. If neither way of connecting receives `Response`
reliably (5 runs out of 5), try `jeepney` in a throwaway venv and record which one works.
Don't add `jeepney` to `pyproject.toml`: that decision goes back to the planner.

### What the answers change

| Answer | Changes |
|---|---|
| Q1 slot style, result types | `ui/portal.py`'s `PortalRequest` and `to_python` in Task 3 |
| Q2 dialog every time | Task 3's README note; Open question 1 in the README is answered |
| Q2 Deny code | `portal.reply_message` wording in Task 3 (both 1 and 2 already map to a refusal) |
| Q3 directory, not a regular file | `portal.load_screenshot`'s checks in Task 3 |
| Q4 image layout | Task 3's `geometry.crop_rect` assumption (one stitched image at one uniform scale) |
| Q5 visible above other windows, no focus | Task 5's `session.ON_SCREEN_DESKTOPS` (add `"gnome"` only if Q5 passed **and** you confirm clicks pass through) |
| Q6 geometry ≠ screen geometry | Task 3 already uses `screen().geometry().topLeft()` for the selector's offset on Wayland; the finding confirms why |
| Q6 when `screen()` / `isVisible()` are right | Task 5's "did the full-screen layer come up" check (first expose, or the 100 ms single-shot) |
| Q7 | whether `summon()` and `explain_screen()` can trust `screen()` |
| Q8 versions and dialog | Task 6's manual check list |
| Q8 app id needed | a Plan change for Task 6 (Registry.Register or a `.desktop` file); README Open question 2 |
| Q9 | Task 2's `xwayland` rule (`capture == "portal"`) |
| Q10 | Task 3's delay before the portal call (`portal.HIDE_DELAY_MS`, 150 today) |
| Q12 | Task 6's `doctor.read_portal_versions` (with or without a temporary `QCoreApplication`) |
| Q13 marshalling | Task 6's `ShortcutsPortal`. If QtDBus can't marshal `a(sa{sv})` both ways, Task 6 needs `jeepney` (optional `wayland` extra). That's a Plan change |
| Q13 object-path type | Task 3's `to_python` (how `QDBusObjectPath` is unwrapped) |

If a finding contradicts a **Contract** in Tasks 3–6, don't change that Contract here.
Write it under [Plan changes needed](#plan-changes-needed). The orchestrator runs a
planner round before that task starts.

## Frontend part (frontend-dev)

The scripts are throwaway-quality but committed, so you can rerun them on KDE. They live
outside `src/` and import nothing from `kami` (see the README's rules).

| File | Change |
|---|---|
| `plans/phase-3/spike/portal_shot.py` | new: Q1–Q4, Q11. Flags `--timeout S` (default 20), `--interactive`, `--layout` |
| `plans/phase-3/spike/layer_probe.py` | new: Q5, Q6, Q10. Flags `--timeout S`, `--hide-delay MS`, `--hold S` (just show the square for S seconds, no screenshot, for your click test) |
| `plans/phase-3/spike/where_am_i.py` | new: Q7. Opens a small window for 5 s, prints `QCursor.pos()` and `screen().name()` before and after `show()` |
| `plans/phase-3/spike/xwayland_grab.py` | new: Q9. Must be run with `QT_QPA_PLATFORM=xcb` (it exits with a message otherwise) |
| `plans/phase-3/spike/portal_versions.py` | new: Q8, Q12. Prints `Screenshot`, `GlobalShortcuts`, `ScreenCast` versions or `missing`. `--no-app` reads them before any `QCoreApplication` exists |
| `plans/phase-3/spike/marshal_check.py` | new: Q13. Registers `org.kami.Spike` on the session bus, echoes one `(o, a(sa{sv}), a{sv})` call, prints the wire signature and the Python types in the reply, then unregisters |
| `plans/phase-3/spike/shortcut.py` | new: Q8 on KDE only. `CreateSession` → `BindShortcuts` (`toggle`, preferred `CTRL+ALT+k`) → prints `Activated` for 30 s → closes the session. Flag `--register` first calls `Registry.Register("org.kami.Kami", {})` (if the interface exists), to compare |
| `plans/phase-3/task-1-wayland-spike.md` | fill in Findings, How to rerun, Plan changes needed, and tick Done when |
| `plans/phase-3/README.md` | answer Open questions 1–3 if the findings settle them |

Steps:

1. Write `portal_versions.py` first and run it (Q8, Q12). It needs no dialog.
2. Write `portal_shot.py`:
   1. Get the bus's unique name, build the token (`kami_spike_` + 8 hex chars) and the
      request path. Connect `Response` with service `org.freedesktop.portal.Desktop` on
      that path **before** calling `Screenshot`.
   2. Call `Screenshot("", {"handle_token": token, "interactive": False})`.
   3. Use a `QTimer` for the timeout and `QEventLoop` to wait. On timeout, call
      `Request.Close` and exit 3.
   4. On `Response`, print:
      - `response <code>`
      - the `results` key names and the Python type of each value
      - the URI's scheme, its directory, and whether `lstat` says it is a regular file
   5. Apply the checks in "Trusting the reply, and deleting the file", then print
      `deleted True|False`, or `not deleted (<reason>)`.
   6. With `--layout`, decode the bytes with `QImage.fromData` and print the image size
      next to every `QScreen`'s `name()`, `geometry()` and `devicePixelRatio()`.
   7. Read the permission store before the first run and after the third run.
3. Run `portal_shot.py` three times, one after the other (Q2). If the first run times
   out, stop the portal rows (see "The dialog rule").
4. Write `layer_probe.py`:
   1. Show the full-screen click-through window with a magenta (`#FF00FF`) square.
   2. Print the Q6 values at the three moments (straight away, first expose, 100 ms).
   3. Wait 500 ms, then take a portal shot (same reply and delete rules as
      `portal_shot.py`). Print the average RGB inside the square and in a 50×50 control
      area outside it, plus `isActiveWindow()` and `QGuiApplication.focusWindow()`.
   4. With `--hide-delay N`: show for 500 ms, `hide()`, wait N ms, shoot, and print the
      square's average again (Q10). Run it for 0, 150, 300 and 600.
5. Write and run `where_am_i.py` from a terminal (Q7). Then run `xwayland_grab.py` with
   `QT_QPA_PLATFORM=xcb` (Q9: print the pixmap size, `isNull()`, and the share of pixels
   that are pure black).
6. Write and run `marshal_check.py` (Q13). Then write `shortcut.py` with the same
   marshalling (don't run it on GNOME 46: there's no portal). Check that it starts and
   prints `GlobalShortcuts: missing` here.
7. Fill in the Findings table with an answer and evidence (a printed line, a number, a
   version) for every builder row. Write `needs you` in every row or column a builder
   can't answer.
8. Fill in [How to rerun](#how-to-rerun): the exact commands for this machine
   (`.venv-1/bin/python -I …`) and for the KDE VM (`uv run --no-project --with PySide6 python -I …`),
   for each "needs you" cell.
9. Write [Plan changes needed](#plan-changes-needed), or "none".
10. Run `/security-check` on `plans/phase-3/spike/`, then `.venv-1/bin/ruff check .`. The
    scripts must pass, because CI lints the whole repo.

## Tests

None in `tests/`. The spike adds no code under `src/`, and its scripts are run by hand.
Check `.venv-1/bin/python -m pytest -q` still shows 169 passed, and
`.venv-1/bin/ruff check .` is clean.

## Manual check

Builders: none (the scripts check pixels instead of eyes). Yours, from
[How to rerun](#how-to-rerun), collected into `your-checklist.md`:

- [ ] If Q2 says "dialog appeared": run `portal_shot.py` yourself and click **Allow**.
      Run it again and note whether the dialog came back. Run it once more and click
      **Deny** (Q2 Deny code)
- [ ] Q3: after a run, open **Files** → **Pictures** → **Screenshots**, and the
      notification list (click the clock at the top). There should be no new shot from
      the spike. Paste into Text Editor: no image
- [ ] Q5: while `layer_probe.py --hold 10` shows the magenta square, click a window
      under it. The click must reach that window
- [ ] Q11: run `portal_shot.py --interactive --timeout 120`, pick an area, and note the
      printed size
- [ ] KDE VM: run every script (and `shortcut.py` with and without `--register`), and
      fill in the KDE column. In System Settings → Shortcuts, note which app the
      binding is listed under
- [ ] Second monitor or another scale, if you have one: Q4, Q6, Q7

## Security

Run `/security-check` on `plans/phase-3/spike/`. The scripts delete a file whose name
arrives in a D-Bus reply, handle screenshots, and register a test service on the session
bus. Check:

- `Response` is accepted only from `org.freedesktop.portal.Desktop` on the predicted
  path.
- Nothing is deleted without the four URI checks and the `fstat` check.
- No image is saved.
- No full path or file name is printed or written into the Findings.
- `marshal_check.py` unregisters `org.kami.Spike` on exit.

## Findings

Filled in by frontend-dev. Evidence is a printed line, a number or a version.

Measured 2026-10-12, 23:02–23:32, PySide6 6.11.2, xdg-desktop-portal 1.18.4. 18
`Screenshot` calls in total (4 from `portal_shot.py`, 14 from `layer_probe.py`), 18
`Response`s, 18 files deleted, 0 left in `~/Pictures`, no timeouts. There was one dialog
(Q2), and someone at the machine answered it, not a builder. Plus one ScreenCast
`CreateSession` (no dialog) to try `shortcut.py`'s jeepney code.

| # | GNOME 46 (Ubuntu 24.04, this machine) | KDE Plasma 6 (Fedora VM) | Notes |
|---|---|---|---|
| Q1 | **Yes, QtDBus works.** Subscribing before the call on the predicted path (`…/request/1_257/kami_spike_…`) got `Response` 18 times out of 18, and the returned handle (`QDBusObjectPath`) always matched the prediction. Only the **typed slot** can read the results: `@Slot("uint", "QVariantMap")`, connected with `SLOT("on_typed(uint,QVariantMap)")`, gives `code` as `int` and `results` as `dict{'uri': str}`. The `QDBusMessage` slot fires too (`'ua{sv}'`), but its `arguments()` are `[int, QDBusArgument]`, and Python can't read that map. `results` holds one key, `uri: str` | needs you | Two PySide6 traps: the slot must be a `str` from `SLOT()` (`bytes` is refused, whatever the stubs say), and `@Slot(int, …)` is refused for D-Bus `u`; it has to be `"uint"` |
| Q2 | **Dialog the first time, then remembered, but for the app that launched the process, not for Kami.** Run 1: `response 0 after 7577 ms`, two `Failed to associate portal window` lines in the journal (dialog + shot), store `[]` → `['screenshot']`, `Lookup` = `{'com.microsoft.VSCode': ['yes']}`. Runs 2 and 3: `529 ms` / `519 ms`, one journal line, no dialog. The app id comes from the systemd scope: this shell runs in `app-com.microsoft.VSCode-4221.scope`. Deny code: needs you | needs you | Builders can't click, so someone at the machine (idle monitor: 266 ms) clicked **Allow**. Nothing on the bus tells Kami which app id it got |
| Q3 | `uri scheme 'file', host '', directory ~/Pictures/, extension '.png', lstat regular file: True` → `deleted True`, `file still there afterwards: False` (all 4 `portal_shot.py` runs). `deleted True` for all 18 calls. Afterwards, `find ~/Pictures -newermt 23:00` finds 0 files. Notification / clipboard: needs you | needs you | The file goes straight into `~/Pictures/`, **not** `~/Pictures/Screenshots/` |
| Q4 | 1 screen, 100 %: `image 1920x1080`; `screen eDP-1: geometry (0, 0) 1920x1080, devicePixelRatio 1.0` → same size, `k = 1.000` | needs you | 2 screens / 125 % / 200 %: needs you |
| Q5 | **Fails on GNOME 46.** Visible: the square was fully magenta in 4 of 5 shots (`(255, 0, 255)`, 100 % of the square) and dim in 1 (`(86, 28, 85)`). But outside the square, the full-screen layer is **opaque black**: all 6 control spots read `(0, 0, 0)` while it was shown and the normal desktop (22–147 grey levels) when it was hidden. Focus: the layer **took focus in 7 of 9 runs** (`isActiveWindow True; focusWindow the layer`), despite `WA_ShowWithoutActivating`. With plain `show()` instead of `showFullScreen()`, it is see-through, but GNOME shrinks it to `1854x1048` and keeps it **behind** other windows (0 magenta samples, not active). Clicks: needs you | needs you | The same black backing hits `RegionSelector`: with its fill, every spot reads `(11, 10, 16)` (its colour over black), including one where the desktop is `(147, 141, 113)`. See Plan change 3 |
| Q6 | 1 screen: (a) straight after `showFullScreen()`: `geometry (0, 0) 1920x1080; screen eDP-1; geometry == screen geometry True; isVisible True; windowHandle yes, exposed False`. (b) `showEvent` 4 ms after show (inside `showFullScreen()`); first `Expose` **14–23 ms** after show, `isExposed True`. (c) 100 ms: same values, `exposed True` | needs you | `screen()` and `isVisible()` are already right at (a), before the compositor has shown anything. Only `windowHandle().isExposed()` changes, at the first Expose. 2 screens: needs you |
| Q7 | 1 screen: `QCursor.pos() (0, 0)` before `show()`, straight after it, after 300 ms and after 5 s. `screenAt` → `eDP-1` (only because (0, 0) is on it). `availableGeometry (0, 0) 1920x1080` (Qt doesn't know the top bar). The window reports `geometry (1375, 48)` (what `move()` asked for). `isActiveWindow False` straight after `show()`, `True` at 300 ms | needs you | `summon()` and `explain_screen()` can't trust the cursor on Wayland. With 2 screens, `screenAt(QCursor.pos())` would pick the screen at (0, 0). 2 screens: needs you |
| Q8 | `GlobalShortcuts: missing (org.freedesktop.DBus.Error.InvalidArgs: No such interface "org.freedesktop.portal.GlobalShortcuts")`, `Screenshot: v2`, `ScreenCast: v5`, `Registry (org.freedesktop.host.portal.Registry): missing`. `shortcut.py` prints `GlobalShortcuts: missing`. Its jeepney half was run against ScreenCast's `CreateSession` (same shape, no dialog): `returned path same as predicted: True`, `Response after 6 ms`, `session_handle` as an `'s'` variant, `Session.Close: ok` | needs you (version, dialog, app name, with / without `--register`) | GNOME 48+: needs you. From Q2, expect KDE to name the app after the **launching app's scope** (Konsole) unless Kami runs in its own `app-org.kami.Kami-*.scope` |
| Q9 | `QT_QPA_PLATFORM=xcb`: `pixmap 1920x1080, isNull False`; `pure black 100.0%, magenta (own window) 0.0%, anything else 0.0%` of 129 600 samples. All black, **Kami's own windows included** | — (not needed) | Task 2's rule (`capture == "portal"` under XWayland) is right. Without `xcb` the script stops with a message (exit 2) |
| Q10 | 0 ms: gone · 150 ms: gone · 300 ms: gone · 600 ms: gone. 0 magenta samples each time; the square's area shows the desktop (`(32, 32, 32)`, `(31, 33, 34)`, `(32, 31, 31)`, `(31, 33, 34)`). Call → `Response` took 504–784 ms | needs you | The portal itself takes ~0.5 s before it captures, so even 0 ms works here. `HIDE_DELAY_MS = 150` stays |
| Q11 | needs you | needs you | |
| Q12 | **No `QCoreApplication` needed.** `--no-app`: `QCoreApplication exists: False`, `sessionBus connected: True (2.7 ms)`, 3 property reads in `2.4 ms` (0.6–1.1 ms each), no Qt warning. The `version` arrives as a `QDBusVariant`; `.variant()` gives the `int` | — (same Qt) | |
| Q13 | **QtDBus can't send or read `a(sa{sv})`.** Send: A, a list of tuples → `Marshalling failed: Unregistered type PySide::PyObjectWrapper` (and in an earlier single-process version of the check, the next blocking call then hung past its 3 s timeout, 4 runs out of 4). B, a list of lists → wire `'oava{sv}'` (wrong type). C, a `QDBusArgument` struct array → libdbus aborts (`exit code -6`); `arg << "toggle"` even writes `as`, so a `(str, dict)` struct comes out `'(asas)'`. Read: `beginArray()` works, but `beginStructure()` binds to the **write** overload (`write from a read-only object`), and map entries read through `asVariant()` come back `None`. Re-sending a *received* argument works (gdbus got its echo back intact). Object path: bare `o` → `QDBusObjectPath` (method reply; `Activated` gives `osta{sv}`: `QDBusObjectPath`, `str`, `int`, unreadable options). Inside `a{sv}` through the typed slot → `QDBusObjectPath`. **jeepney 0.9.0 does all of it:** `Echo reply signature 'oa(sa{sv})a{sv}'`, `same values back: True`, a nested `a(sa{sv})` in a `Response` reads as `('a(sa{sv})', [('toggle', {...})])`, object paths as `str` | — (same Qt) | The sender filter works in QtDBus: the slot connected with `org.kami.Spike` ignored gdbus's signal and got the owner's. jeepney's local `filter()` needs the sender's **unique** name: `sender='org.kami.Spike'` → `False`, owner's unique name → `True` |

**Task 5's first path: in-panel.** GNOME stays off `ON_SCREEN_DESKTOPS`. The full-screen
layer blacks out the screen and takes focus. KDE goes on the list only once `layer_probe.py`
there prints `square visible in the shot: True`, `transparent outside the square: True` and
`isActiveWindow False`, **and** you confirm that clicks pass through.

**Decisions** (README): 1 (portal only on Wayland) holds; Q9 shows XWayland can't grab.
2 (Kami's own selector) holds only if the selector shows a still copy of the screenshot.
As planned, it would be a black screen on GNOME (Plan change 3). 3 (the compositor places
the panel) holds: GNOME ignored the probe's size and position too. 4 is not affected.

**README Open questions.** 1: GNOME 46 asks once, then remembers, but per *launching app*
(`com.microsoft.VSCode` here). So the answer depends on how Kami is started (Plan change 5).
2: still open (KDE); there's no `Registry` on xdg-desktop-portal 1.18.4.
3: no, not with a full-screen layer on GNOME 46, so it gets in-panel doodles.

### How to rerun

On this machine, from the repo root: `.venv-1/bin/python -I plans/phase-3/spike/<script>.py`.
On the KDE VM, from the clone's root (there's no `.venv-1`):
`uv run --no-project --with PySide6 --with jeepney python -I plans/phase-3/spike/<script>.py`
(jeepney is needed by `shortcut.py` only, and adds a step to `marshal_check.py`; it is never
added to `pyproject.toml`). You're there to click, so use `--timeout 60` where a dialog can
appear. Builders keep 20 s. Exit code 3 means `TIMEOUT` (the dialog was closed for you).

| Needs you | Where | Command (this machine; on KDE swap in the `uv run …` prefix) | Look for |
|---|---|---|---|
| Q2 Deny code | GNOME | The grant for VS Code is stored, so first remove it:<br>`gdbus call --session --dest org.freedesktop.impl.portal.PermissionStore --object-path /org/freedesktop/impl/portal/PermissionStore --method org.freedesktop.impl.portal.PermissionStore.DeletePermission screenshot screenshot com.microsoft.VSCode`<br>then `… portal_shot.py --timeout 60` and click **Deny** | `response 1` or `response 2`. Run it again and click **Allow** (or leave the grant removed, see Try by hand) |
| Q2 from a terminal | GNOME | Open **Terminal** (not VS Code) and run `… portal_shot.py --timeout 60` | Does a dialog appear, which app does it name, and what is under `permission store after`? Then `gdbus call … PermissionStore.Lookup screenshot screenshot` shows the app id |
| Q2, Q1–Q4 | KDE | `… portal_shot.py --timeout 60 --layout`, three times | First run: dialog or not, `response`, `results keys`, `directory`. Runs 2–3: does the dialog come back? |
| Q3 copies | both | After a `portal_shot.py` run: open **Files → Pictures** (KDE: the folder in `directory`), the notification list (GNOME: click the clock), and paste into Text Editor | No new screenshot file, no screenshot notification with a thumbnail, no image on paste |
| Q4 | 2 screens or 125 % / 200 % | `… portal_shot.py --layout` | `image WxH` next to each `screen …` line: one stitched image of all screens? `x dpr` sizes? |
| Q5 clicks | GNOME | `… layer_probe.py --hold 10` | **The screen goes black except a magenta square for 10 s** (that's the Q5 finding). Click a window under it: does the click reach it? Do you see black too? Esc does nothing; it closes itself |
| Q5, Q6, Q10 | KDE | `… layer_probe.py`, then `… layer_probe.py --hold 10` (click test), then `… layer_probe.py --hide-delay N` for N = 0, 150, 300, 600 | `square visible in the shot`, `transparent outside the square`, `isActiveWindow`, the (a)/(b)/(c) lines, and for Q10 `square visible … False` |
| Q6, Q7 | 2 screens | `… layer_probe.py`, and from a terminal on the **second** screen with the mouse there: `… where_am_i.py` | Q6: does `screen` match the target, and `geometry == screen geometry`? Q7: does `QCursor.pos()` stay `(0, 0)`, and which screen does `summon() picks`? |
| Q7 | KDE | `… where_am_i.py` | Same lines as on GNOME |
| Q8 | KDE (and GNOME 48+) | `… portal_versions.py`, then `… shortcut.py --timeout 60`: accept the dialog and press **Ctrl+Alt+K** within 30 s. Then `… shortcut.py --timeout 60 --register` | `GlobalShortcuts: vN`, whether a dialog appeared, `bound 'toggle': trigger_description …`, `Activated 'toggle', ours: True`, and in **System Settings → Shortcuts**, which app the binding is listed under (with and without `--register`) |
| Q11 | both | `… portal_shot.py --interactive --timeout 120 --layout` and pick an area | `image WxH` should be the area you picked, not the full screen. Same `uri` / `deleted` lines as Q3 |
| Q13 (optional) | KDE | `uv run --no-project --with PySide6 --with jeepney python -I plans/phase-3/spike/marshal_check.py` | Same as here; ends with `org.kami.Spike gone from the bus: True` |

### Plan changes needed

1. **Task 6, Contract and step 1.3** (`ShortcutsPortal`: "`BindShortcuts` through
   `PortalRequest`, with the shortcut list as `a(sa{sv})`, marshalled the way Task 1, Q13
   found to work"; "`results["shortcuts"]` is `list[tuple[str, dict]]`"). Q13: PySide6
   6.11.2 QtDBus can neither send `a(sa{sv})` (marshal error, wrong `av`, or a libdbus
   abort) nor read one (`beginStructure()` binds to the write overload). jeepney 0.9.0 does
   both. So Task 6 needs jeepney (an optional `wayland` extra), at least for `CreateSession`
   / `BindShortcuts` and their `Response`s. Notes for the planner: jeepney gives variants
   as `(signature, value)` tuples and object paths as `str`; its local `filter()` must use
   the portal's unique name (`GetNameOwner`), not `org.freedesktop.portal.Desktop`; and the
   portal session belongs to the connection that created it, so every call of one session
   has to go through jeepney.
2. **Task 3, Contract `to_python`** ("`QDBusArgument` → demarshalled by its current type:
   structure → tuple, array → list, map → dict (the way Task 1, Q13 found to work)"). Not
   possible in PySide6 6.11.2 (Q13). For Task 3 it doesn't matter: through the typed slot
   the Screenshot results are `{'uri': str}`. So `QDBusArgument` should become `None`
   (dropped) here. The Manual check line "`to_python` … `list[tuple[str, dict]]` for the
   shortcuts" can't pass with QtDBus; it belongs with Task 6's jeepney code. Also for
   `PortalRequest` step 2.2: the slot style that works is `@Slot("uint", "QVariantMap")`
   with `SLOT("<name>(uint,QVariantMap)")` as a `str`. A `QDBusMessage` slot can't read the
   results. And never pass QtDBus a value it can't marshal (a tuple, for one): the failed
   call can leave the next blocking call stuck past its timeout.
3. **Task 3, Design steps 1–3 and `region_select.py`** (`RegionSelector.start(screen)` →
   `setScreen` + `setGeometry` + `showFullScreen()` over the live desktop, then the portal
   shot after `HIDE_DELAY_MS`). On GNOME 46 a translucent full-screen window is backed by
   **opaque black** (Q5). With the selector's fill, the whole screen reads `(11, 10, 16)`,
   so you would drag a box over a black screen. Suggested change: on Wayland, take the
   portal screenshot **first** (panel hidden), then show the selector full-screen with that
   screenshot painted as its own background (dimmed as today), and crop the same image.
   That also makes `HIDE_DELAY_MS` matter less (Q10), and the crop can't drift. Without
   it, Decision 2 doesn't work on GNOME. The X11 path stays as it is.
4. **Task 5, Design "Two ways" 1 and step 2.4** ("On Wayland, `screen()` and `isVisible()`
   only become true after the compositor maps the window"; `_check_layer` tests
   `windowHandle()`, `isVisible()`, `screen()`). Q6: all three are already right straight
   after `showFullScreen()`, before anything is on screen. Only
   `windowHandle().isExposed()` flips, at the first Expose (14–23 ms). So the check should
   test `isExposed()`. `LAYER_CHECK_MS = 100` is enough. The check also can't see the black
   backing or the focus grab from Q5, so a desktop joins `ON_SCREEN_DESKTOPS` only after
   `layer_probe.py` there shows the square, `transparent outside the square: True` and
   `isActiveWindow False`, plus your click check. `ON_SCREEN_DESKTOPS` stays empty
   (GNOME failed).
5. **Task 6, "App id", and README Open question 1** ("This task builds the flow without
   registering"). Q2: xdg-desktop-portal 1.18.4 already takes an unsandboxed app's id from
   its systemd scope (`app-com.microsoft.VSCode-4221.scope` → `com.microsoft.VSCode`), and
   `Registry` doesn't exist there. So the screenshot dialog names, and the grant goes to,
   whatever launched Kami: VS Code, the terminal, or the autostart entry. KDE will likely
   do the same for shortcuts. To get one stable "Kami" grant, Kami needs an
   `org.kami.Kami.desktop` file and should run in an `app-org.kami.Kami-<n>.scope` (started
   from that desktop file, or `systemd-run --user --scope --unit=app-org.kami.Kami-$$ kami`).
   That affects Task 3's README note (which app the dialog names) and Task 6. Phase 7's
   autostart needs the `.desktop` file anyway.

## Done when

- [x] Every "builder" row in the Findings table has an answer and its evidence, or "dialog
      appeared (no Response in 20 s)" and the matching "needs you" step
- [x] Every "needs you" cell has a matching command in How to rerun
- [x] Plan changes needed is filled in (or says "none")
- [x] The README's [Decisions](README.md#decisions-accepted-2026-10-12) still hold, or a
      Plan change explains why one doesn't
- [x] Task 5 knows which path to build first: on-screen layer, in-panel, or both
- [x] `/security-check` on `plans/phase-3/spike/` passes
- [x] `.venv-1/bin/ruff check .` is clean and 169 tests still pass (202 after Task 2)

## Commits

1. `add wayland spike scripts`
2. `record wayland spike findings`
