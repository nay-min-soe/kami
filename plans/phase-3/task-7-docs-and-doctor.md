# Task 7 — `kami doctor`, README, tested desktops and a stable app id

**Size:** S · **Depends on:** Task 3, Task 4, Task 5, Task 6 · **Branch:** `wayland-docs` · **Owner:** backend

## Goal

Someone on any Linux desktop can tell, from the README and `kami doctor`, what Kami does
there: how it captures, where the doodles go, and how the hotkey works. If something is
missing, they get the exact fix. Kami also ships an `org.kami.Kami.desktop` file, and the
README explains how to start Kami *as Kami*, so the desktop files its screenshot (and
hotkey) permission under one stable name.

## Why

- `check_screen_grab` still says *"Wayland: … may capture a blank image (portal support is
  Phase 3)"*, even after Task 3.
- Doctor has no row for where the doodles go (Task 5).
- The README's Wayland notes say portal capture is "on the roadmap". The roadmap list
  still has "Wayland screen capture via the XDG desktop portal" unticked, and there's no
  tested-desktops table.
- **The permission follows the launcher, not Kami** (Task 1, Q2, Plan change 5).
  xdg-desktop-portal 1.18.4 takes an unsandboxed app's id from its systemd scope. On this
  machine the screenshot grant was stored for `com.microsoft.VSCode`, because Kami was
  started from VS Code. Started from a terminal or an autostart entry, Kami can be asked
  again, and the dialog names the wrong app. A desktop file with a stable id, plus
  starting Kami in a matching scope, fixes that. Phase 7's autostart needs the file
  anyway. There's no `Registry` interface on 1.18.4 (Q8), so registering from code isn't
  an option here.

## Design

### Stable app id (the smallest version)

- **Ship** `packaging/org.kami.Kami.desktop`:

  ```ini
  [Desktop Entry]
  Type=Application
  Name=Kami
  Comment=Hotkey-summoned AI sidekick
  Exec=kami
  Terminal=false
  Categories=Utility;
  StartupNotify=false
  ```

  No icon yet: Phase 7 brings the real icon. Kami's code doesn't read this file, and
  nothing installs it automatically.
- **Document** two ways to start Kami as `org.kami.Kami`, in a README section "One
  permission for Kami (Wayland)":
  1. Copy the file to `~/.local/share/applications/` and start **Kami** from the app grid.
     The desktop launches desktop entries in their own scope.
  2. From a terminal or a custom shortcut:
     `systemd-run --user --scope --unit=app-org.kami.Kami-$$ kami`.

  Whether GNOME's dialog then names "Kami", and the grant shows up under
  `org.kami.Kami`, is your hand check. The README states only what was checked.
- Not in this phase: a `kami install` command, autostart, changing how `kami` launches
  itself. Those are Phase 7.

### `kami doctor`

Four rows, one fact each, with the fix when something's missing. GNOME 46 Wayland (this
machine) should print:

```
Session       ✓ wayland · gnome
Screen grab   ✓ portal (Screenshot v2) · the desktop asks once per app that starts Kami
Doodles       ⚠ in the panel: GNOME on Wayland doesn't let apps draw over other windows, …
Hotkey        ⚠ GNOME 46 and older can't give apps a global hotkey. Add one in Settings → …
```

`check_screen_grab(env, portals)`:

| Session | Screenshot portal | Row |
|---|---|---|
| x11 | — | `✓ X11` (today's text) |
| wayland | version N | `✓ portal (Screenshot vN) · the desktop asks once per app that starts Kami` |
| wayland | missing (`None`) | `✗ no Screenshot portal → install <package>` |
| wayland | not checked (`portals` is `None`) | `⚠ portal not checked` |
| unknown | — | today's warning |

- `<package>` by desktop: gnome → `xdg-desktop-portal-gnome`, kde →
  `xdg-desktop-portal-kde`, sway → `xdg-desktop-portal-wlr`, hyprland →
  `xdg-desktop-portal-hyprland`, other → *"the xdg-desktop-portal backend for your
  desktop"*. The pure helper `session.portal_package(desktop)` returns it.
- With `xwayland`, the row adds ` · Qt runs on XWayland`. Capture still goes through the
  portal (Q9: `grabWindow` is pure black there).

`check_doodles(env)`: `plan = doodle_plan(detect(env), True, env)`:

| plan | Row |
|---|---|
| screen, X11 / unknown | `✓ on screen` |
| screen, Wayland (only with `KAMI_DOODLES=screen`) | `⚠ on screen (KAMI_DOODLES=screen, a test switch)` |
| panel, `desktop` | `⚠ in the panel: <panel_note(session, "desktop")>` |
| panel, `forced` | `– in the panel (KAMI_DOODLES=panel)` |

The row reflects a capture made with Kami's own selector. Picker captures are always in
the panel, and the README says so.

Doctor reads the portal versions once (Task 6 reads them in `collect`, crash handling
included), and this task passes them on to the screen-grab row too.

### README

- "What it does" table: Explain screen → *"✅ Works (X11 and Wayland; see Desktops)"*.
- Replace "Hotkey: X11 vs Wayland" (written in Task 6) with a **"Desktops"** section
  holding this table plus the hotkey text. The cells already filled come from Task 1's
  Findings (measured 2026-10-12). Your hand checks fill the rest.

| Desktop | Capture | Doodles | Hotkey | Tested |
|---|---|---|---|---|
| GNOME 46, X11 | `grabWindow` | on screen | built-in (pynput, `kami[hotkey]`) | |
| GNOME 46, Wayland | portal; you drag on a still copy of the screen | in the panel (on-screen layer goes black, Task 1 Q5) | custom shortcut (no portal) | |
| GNOME 48+, Wayland | portal | in the panel | portal (`kami[wayland]`) | not tested yet |
| KDE Plasma 6, Wayland | portal | in the panel | portal (`kami[wayland]`) | |
| Sway | portal (`-wlr`) | in the panel | custom shortcut | best effort, not tested yet |
| Hyprland | portal | in the panel | portal (`kami[wayland]`) | best effort, not tested yet |

  - Write a date in **Tested** only where a hand check was really done (your-checklist
    ticks). Otherwise write *"not tested yet"*. Never guess.
  - A cell the spike or a hand check didn't confirm gets *"(expected)"* after it.
- Wayland notes:
  - Explain screen takes the screenshot first, then you drag on the still image
  - the permission dialog, asked once **per app that starts Kami** (Q2), and the "One
    permission for Kami" section
  - the screenshot file goes to `~/Pictures/` for a moment and Kami deletes it (Q3)
  - where the doodles appear and why
  - the panel opens where the desktop puts it (Decision 3)
  - `KAMI_DOODLES=panel` / `screen`, with the GNOME 46 warning for `screen`
  - the hotkey: `pip install 'kami[wayland]'`, and the desktop's own dialog
- The "One permission for Kami (Wayland)" section from Design.
- Roadmap list: tick "Wayland screen capture via the XDG desktop portal".

### Other docs

- `ARCHITECTURE.md`:
  - `ui/portal.py` box in the UI layer (Screenshot)
  - `session.py`, `portal.py` and `portal_shortcuts.py` boxes in Core, with arrows Panel
    → Session, Panel → `ui/portal.py` → `portal.py`, Hotkey → `portal_shortcuts.py` →
    `portal.py`
  - `hotkey.py` box text: "global hotkey (X11: pynput; Wayland: portal via jeepney, or
    `kami toggle`)"
  - the line "Works on X11. On Wayland the screenshot comes back black" goes
  - **Libraries** table: `QtDBus` (part of PySide6) for the Screenshot portal and
    doctor; `jeepney` (optional `wayland` extra) for GlobalShortcuts, if Task 6 didn't
    already add it
  - **Where things live** table: `packaging/org.kami.Kami.desktop`
- `MILESTONES.md`: tick the Phase 3 bullets whose code is merged. **Don't** tick the exit
  criteria. They need your hand checks on GNOME and KDE.
- `plans/task-recaps.md` gets its entries from `/task-recap` at the end of each
  `/dev-loop`, not from this task.
- `plans/phase-3/your-checklist.md` is extended by `/my-checklist 3` after this task, not
  by the builders.

## Backend part (backend-dev)

| File | Change |
|---|---|
| `packaging/org.kami.Kami.desktop` | new: the entry in Design |
| `src/kami/session.py` | `portal_package(desktop) -> str` |
| `src/kami/doctor.py` | `check_screen_grab(env, portals)`, new `check_doodles(env)`, `collect` passes the versions to the screen-grab row; module docstring mentions the portal check |
| `tests/test_doctor.py` | the rows for X11, GNOME 46, KDE, and no portal |
| `tests/test_session.py` | `portal_package` cases |
| `tests/test_packaging.py` | new: the desktop file parses and names Kami |
| `README.md` | Explain screen row, Desktops section and table, Wayland notes, "One permission for Kami", roadmap tick |
| `ARCHITECTURE.md` | boxes, arrows, libraries, Explain-screen text, where things live (see Design) |
| `MILESTONES.md` | Phase 3 bullets whose code is merged |

Steps:

1. Write the tests below first.
2. Add `packaging/org.kami.Kami.desktop` exactly as in Design.
3. `session.portal_package(desktop)`: the mapping in Design.
4. `doctor.check_screen_grab(env, portals=None)`: the table in Design. The X11 and
   unknown texts stay word for word.
5. `doctor.check_doodles(env)`: the table in Design. Insert it in `collect` right after
   the screen-grab row, through `guarded`.
6. In `collect`, pass the `versions` Task 6 already reads on to `check_screen_grab`, the
   same way Task 6 passes them to `check_hotkey`. Don't read the portals a second time,
   and don't add another try / except.
7. Run `.venv-1/bin/python -m kami doctor` on this machine and paste its four rows into
   the PR description. They must match the Design's sample.
8. Update the README, `ARCHITECTURE.md` and `MILESTONES.md` as in Design (`/docs-sync`).
   For the desktops table, read Task 1's Findings and the ticked Manual check boxes in
   Tasks 3–6 and `your-checklist.md`.
9. `.venv-1/bin/python -m pytest -q` and `.venv-1/bin/ruff check .`.

## Tests

- [ ] `test_portal_package_per_desktop` in `tests/test_session.py`
- [ ] `test_desktop_file_names_kami` in `tests/test_packaging.py`:
  - `configparser` (with `interpolation=None`) reads `packaging/org.kami.Kami.desktop`
  - `[Desktop Entry]` has `Type=Application`, `Name=Kami` and `Exec=kami`
  - the file name minus `.desktop` is `org.kami.Kami`
- [ ] `test_doctor_x11_rows` in `tests/test_doctor.py` (screen grab `✓ X11`, doodles `✓ on screen`)
- [ ] `test_doctor_gnome46_wayland_rows` (`{"Screenshot": 2, "GlobalShortcuts": None}` → screen grab ✓ v2 "asks once per app", doodles ⚠ panel naming GNOME, hotkey ⚠)
- [ ] `test_doctor_kde_wayland_rows` (both portals, `has_jeepney=True` → screen grab ✓, hotkey ✓)
- [ ] `test_doctor_wayland_no_screenshot_portal_fails` (✗, names `xdg-desktop-portal-gnome`; exit code 1)
- [ ] `test_doctor_wayland_portals_not_checked_warns` (no `portals` → ⚠ "not checked")
- [ ] `test_doctor_doodles_forced_panel_is_info` (`KAMI_DOODLES=panel`)
- [ ] `test_doctor_doodles_screen_switch_warns` (`KAMI_DOODLES=screen` on Wayland → ⚠ "test switch")
- [ ] `test_doctor_xwayland_note` (`QT_QPA_PLATFORM=xcb` on Wayland → screen grab mentions XWayland)

## Manual check

**Builder checks: no window, no portal call.** `kami doctor` opens no window, and it
reads two properties only.

- [ ] `.venv-1/bin/python -m kami doctor` prints the four rows in the Design's sample
      (Screenshot v2, GNOME panel note, GNOME hotkey fix)
- [ ] `KAMI_DOODLES=panel .venv-1/bin/python -m kami doctor` shows
      `Doodles – in the panel (KAMI_DOODLES=panel)`
- [ ] `desktop-file-validate packaging/org.kami.Kami.desktop` prints nothing, if the tool
      is installed. If it isn't, say so in the report
- [ ] Every row of the README desktops table has a date, "not tested yet" or
      "(expected)" where nothing was measured

Yours (in `your-checklist.md`):

- [ ] Copy `packaging/org.kami.Kami.desktop` to `~/.local/share/applications/` and start
      **Kami** from the app grid. Remove the VS Code grant first (Task 1's How to rerun,
      Q2). Does the screenshot dialog name "Kami"? Then run
      `gdbus call --session --dest org.freedesktop.impl.portal.PermissionStore --object-path /org/freedesktop/impl/portal/PermissionStore --method org.freedesktop.impl.portal.PermissionStore.Lookup screenshot screenshot`
      and check which id the grant is stored under
- [ ] The same with `systemd-run --user --scope --unit=app-org.kami.Kami-$$ kami`
- [ ] `kami doctor` on KDE Wayland and on X11 matches the README table
- [ ] Fill in the "Tested" dates for the rows you checked (or tell Claude the results)

## Security

None for code. Doctor reads two D-Bus property values through Task 6's reader and
prints versions and fixed texts. The desktop file runs only `kami`. Nothing private is
printed.

## Done when

- [ ] All tests above pass with the earlier ones, and ruff is clean
- [ ] `kami doctor` on this machine matches the Design sample
- [ ] `packaging/org.kami.Kami.desktop` exists and passes its test
- [ ] The README has the Desktops table with no guessed cells, the "One permission for
      Kami" section, and the roadmap tick
- [ ] `/docs-sync` reports nothing out of date
- [ ] Your hand checks: Phase exit criterion 1 is ticked in the
      [README](README.md#phase-exit-criteria) (Explain screen works on GNOME Wayland and
      KDE Wayland)

## Commits

1. `report capture and doodle method in doctor`
2. `add a desktop file for a stable app id`
3. `document tested desktops`
