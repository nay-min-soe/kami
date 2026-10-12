# Phase 3 — Wayland support (v0.4)

Goal: Kami works on a default Ubuntu / Fedora desktop, which is Wayland. See
[MILESTONES.md](../../MILESTONES.md#phase-3--wayland-support-v04).

## Baseline (2026-10-13)

- Branch `phase-3-wayland`, stacked on PR #20 (`ask-after-capture`, Phase 2 Task 8, not
  merged yet). Phase 2 Tasks 1–7 are merged (#12–#19). Every Phase 3 task branch stacks on
  top of #20 until it is merged.
- **Task 1 (spike) is done** (scripts in `plans/phase-3/spike/`, commit `0bd5417`;
  findings in [task-1](task-1-wayland-spike.md#findings)). **Task 2 is built**
  (`session.py`; commits `24b08e2`, `82526c1`, `2fa5b30`).
- **202 tests pass** with `.venv-1/bin/python -m pytest -q`, and `.venv-1/bin/ruff check .`
  is clean. The project venv `.venv-1` has every base and dev dependency. Use these two
  commands everywhere in this phase.
- Explain screen (after PR #20): drag a box → `_capture_region` grabs it with
  `screen.grabWindow` **before** the panel comes back → the panel holds
  `self._capture = (png, region, screen_geometry)` and waits for a typed question →
  `_ask_about_capture` runs `learning.explain_region(client, png, question)` in the worker →
  `_show_lesson` draws doodles with `AnnotationLayer.show_annotations(region, items, where)`.
- On Wayland that grab gives an empty pixmap (pure black under XWayland, Q9), and the
  panel shows `session.capture_failed_message`.
- The hotkey needs a hand-made desktop shortcut to `kami toggle`. `HotkeyListener.start()`
  returns `session.hotkey_fallback_message(session)` on Wayland.
- After Task 2, `XDG_SESSION_TYPE` is read only in `session.py`. The only D-Bus code is
  in the spike scripts.

### Facts about the build machine (checked 2026-10-12 / 13)

Builders (backend-dev, frontend-dev, qa-tester) run on this machine.

| | |
|---|---|
| Desktop | Ubuntu 24.04, GNOME Shell 46.0, Wayland (`XDG_CURRENT_DESKTOP=ubuntu:GNOME`, `WAYLAND_DISPLAY=wayland-0`, `DISPLAY=:0` for XWayland) |
| Monitors | **one**: `eDP-1`, 1920×1080, scale 1.0 (Qt `devicePixelRatio` 1.0, platform `wayland`) |
| Portal | `xdg-desktop-portal` 1.18.4, `xdg-desktop-portal-gnome` 46.2, `xdg-desktop-portal-gtk` 1.15.1. No `org.freedesktop.host.portal.Registry` |
| `org.freedesktop.portal.Screenshot` | version **2** ✓. Call → `Response` in 0.5–0.8 s. The PNG lands straight in `~/Pictures/` (Q3, Q10) |
| Screenshot permission | **granted, for `com.microsoft.VSCode`** (Q2): the portal files it under the *launching* app's systemd scope. Builders' shells run in that scope, so builders' portal calls are silent now |
| `org.freedesktop.portal.ScreenCast` | version 5 (not used in this phase) |
| `org.freedesktop.portal.GlobalShortcuts` | **missing** (`No such interface`). GNOME only gets it in GNOME 48 |
| D-Bus from Python | `PySide6.QtDBus` (6.11.2) works for Screenshot through a typed slot (Q1). It **can't** marshal `a(sa{sv})` (Q13). `jeepney` 0.9.0 can, but it isn't installed in `.venv-1` yet: Task 6 adds it as the `wayland` extra |
| Translucent full-screen windows | **opaque black** outside what's drawn, and they take focus (Q5). This rules out on-screen doodles and a live-screen selector on GNOME |
| Input tools | no `ydotool` / `wtype`: builders **can't** drag, click or press keys on the desktop |
| API key | not set in the builders' shell (`kami doctor`: `API key ✗`). Builders get no real answers; `KAMI_DEBUG_DOODLES=1` needs no key |
| Run Kami from the repo | `.venv-1/bin/kami [doctor]` or `.venv-1/bin/python -m kami [doctor]` |

So builders can run silent portal calls and read pixels from the result. They **can't**
click a dialog, drag a region, look at the screen, test a second monitor or another
scale, or log into X11 or KDE. All of that is under "Needs from you".

## Tasks

| # | Task | Size | Owner | Depends on |
|---|---|---|---|---|
| 1 | [Wayland spike: measure what works](task-1-wayland-spike.md) ✅ | S | frontend | — |
| 2 | [Session detection in one place](task-2-session-detection.md) ✅ | S | both | — |
| 3 | [Screen capture through the portal](task-3-portal-capture.md) | M | both | 1, 2 |
| 4 | [The desktop's picker when capture is refused](task-4-picker-fallback.md) | S | frontend | 3 |
| 5 | [Doodles on Wayland, or in the panel](task-5-wayland-doodles.md) | M | both | 1, 3, 4 |
| 6 | [Hotkey through `GlobalShortcuts`](task-6-global-shortcuts.md) | M | both | 1, 2, 3 |
| 7 | [`kami doctor`, README, tested desktops and a stable app id](task-7-docs-and-doctor.md) | S | backend | 3, 4, 5, 6 |

Suggested order: (1 ✅, 2 ✅) → 3 → 4 → 5 → 6 → 7.

- **Task 3** is the core of the phase. Because of Q5, Wayland capture now runs in a
  different order: the portal screenshot first, then Kami's selector over that **still
  image**, then the crop (Decision 2, updated). X11 is unchanged.
- **Task 4** adds the **Use the desktop's picker** button for when the portal refuses.
- **Task 5** builds the in-panel doodles, which is what every Wayland desktop gets in
  this phase: GNOME failed the on-screen test (Q5), and KDE hasn't been measured. The
  full-screen layer stays behind `ON_SCREEN_DESKTOPS` (empty) and the
  `KAMI_DOODLES=screen` test switch.
- **Task 6** needs `jeepney` (optional `wayland` extra), because QtDBus can't speak
  `BindShortcuts` (Q13). On this GNOME 46 it only shows the fallback, so its real check
  needs KDE. It waits for Task 3 only because it adds to `portal.py`.
- **Task 7** writes down what the checks found, ships `org.kami.Kami.desktop` for a
  stable permission, and closes the phase.

## Rules for every task

Same as [Phase 2](../phase-2/README.md#rules-for-every-task), plus:

- **Builders never show a window on the user's real display.** (The user was
  interrupted by flashing windows during the spike.)
  - Every UI check a builder runs uses `QT_QPA_PLATFORM=offscreen`.
  - That includes starting Kami itself (`QT_QPA_PLATFORM=offscreen timeout 20
    .venv-1/bin/python -m kami`).
  - Anything that has to be seen or clicked goes to the task's Manual check under
    "Yours", and into `your-checklist.md`.
- **Live portal calls: at most 3 per task**, and only where the task file lists one.
  - They are silent now that the grant exists (Q2).
  - Every file they produce is deleted with the plan's checks (`portal.load_screenshot`,
    or the spike's equivalent).
  - Each has a 20 s timeout. On timeout the caller sends `Request.Close`, which closes any
    dialog. A timeout means a dialog appeared: don't retry. Record "needs you: Allow" in
    the build report and go on without the live check.
  - Kami itself waits 60 s, because the user may be reading a dialog.
- **Layers.** This phase adds three core modules and one UI module:

  | New file | Layer | Owner | Holds |
  |---|---|---|---|
  | `src/kami/session.py` ✅ | core (no Qt) | backend-dev | session detection, capture / hotkey / doodle choices, user-facing texts |
  | `src/kami/portal.py` | core (no Qt) | backend-dev | portal tokens and request paths, reply parsing, `unwrap_vardict`, reading and deleting the screenshot file |
  | `src/kami/portal_shortcuts.py` | core (no Qt; optional `jeepney`) | backend-dev | the GlobalShortcuts client on its own thread (Task 6) |
  | `src/kami/ui/portal.py` | UI (QtDBus) | frontend-dev | `to_python`, `PortalRequest`, `ScreenshotPortal` |

  - Each task adds its module to the core list in `ARCHITECTURE.md` ("The one rule for
    layers").
  - `doctor.read_portal_versions()` (Task 6, backend-dev) is the one other QtDBus reader.
    `kami doctor` runs without the Qt app, so it reads two `version` properties itself.
    It imports QtDBus inside the function, like `check_running`, and needs no
    `QCoreApplication` (Q12).
  - The spike scripts aren't part of Kami.
- **QtDBus rules** (Q1, Q13; details in Task 3):
  - Read a `Response` only through a typed `@Slot("uint", "QVariantMap")`.
  - Never pass QtDBus a value it can't marshal (tuples, structs, `a(sa{sv})`).
  - `to_python` drops a `QDBusArgument`.
- **X11 must not regress.** Every task keeps the X11 path's code as it is: each X11
  branch is the old code, moved but not changed. Builders can't log into X11, so the X11
  hand checks (calibration ≤ 3 px with `KAMI_DEBUG_DOODLES=1`, hotkey, fade / Keep /
  Clear) are in `your-checklist.md`, once per merged task.
- **Screenshots stay in memory.**
  - The Screenshot portal writes a PNG to `~/Pictures/` and returns its `file://` URI.
    Kami reads it, deletes that one file at once, and never logs its path, URI or
    contents. `portal.load_screenshot` is the only Kami code that touches that file.
  - The full-screen still image (Task 3) lives only until the crop or the cancel.
- **Pure where possible.** Reply parsing, shortcut strings, crop rectangles, doodle
  choices and every user-facing message are pure functions in `session.py`, `portal.py`
  and `geometry.py`, so CI tests them without a desktop.
- **Dependencies.** One new **optional** dependency in this phase: `jeepney>=0.9` in a
  `wayland` extra (Task 6). The base install stays PySide6 + httpx. CI installs
  `.[dev,wayland]`.
- **Tests:** `.venv-1/bin/python -m pytest -q` and `.venv-1/bin/ruff check .` must be clean.
- Run `/security-check` on Tasks 3, 4, 5 and 6. They delete files named over D-Bus,
  handle screenshots, draw model output, add a dependency, or act on D-Bus signals.

## Phase exit criteria

From [MILESTONES.md](../../MILESTONES.md#phase-3--wayland-support-v04):

- [ ] Explain screen works on GNOME Wayland and KDE Wayland
- [ ] Where on-screen doodles can't work, the user gets the in-panel version and is
      told why

## Decisions (accepted 2026-10-12)

The user accepted these as written, and the roadmap runs on its own through Phase 7.
Decision 2 was updated on 2026-10-13 from the spike (Plan change 3). The intent is the
same, but the order of steps on Wayland changed.

1. **The portal is used only on Wayland.** X11 keeps `grabWindow`, which needs no
   permission dialog and is already calibrated. (Q9: under XWayland `grabWindow` is pure
   black, so XWayland counts as Wayland.)
2. **Kami keeps its own region selector.**
   - **On Wayland**, Kami first takes a full screenshot through the portal, without the
     desktop's own picker (`interactive: false`). It then shows that **still image**
     full-screen, you drag your box on it, and Kami crops the same image. (Updated
     2026-10-13: GNOME 46 backs a translucent full-screen window with black (Q5), so a
     selector over the live screen would show a black screen.)
   - **On X11**, the selector stays over the live screen, as today.
   - The desktop picker (`interactive: true`) is the fallback for when Kami's own shot
     is refused (Task 4). That picker doesn't tell Kami *where* the region was, so it
     always gets in-panel doodles.
3. **The panel position is the compositor's choice on Wayland.** Apps can't move their
   own windows there, so `summon()`'s `move()` is ignored. GNOME ignored the probe's size
   and position too (Q5, Q7). This gets documented rather than worked around.
4. **Sway and Hyprland are "best effort".** They go in the tested-desktops table, but
   they are not exit criteria.

## Needs from you

Step by step: **[your-checklist.md](your-checklist.md)**. It holds the getting-ready part
and the spike's "needs you" rows. `/my-checklist 3` adds each task's hand checks once
Tasks 3–7 are built. In short:

- **Merge PR #20 first.** Every Phase 3 branch is stacked on it.
- **The spike's "needs you" rows** on this machine:
  - the Q2 Deny code, and Q2 from a plain Terminal
  - Q3 leftovers (Files → Pictures, the notification list, the clipboard)
  - Q5 clicks
  - Q11 picker size

  Commands are in Task 1's [How to rerun](task-1-wayland-spike.md#how-to-rerun).
- **Hand checks on this GNOME 46 Wayland desktop**: drag a box on the still image, answer
  a dialog, look at the panel doodles. These are listed under each task's "Manual check".
- **A KDE Plasma 6 Wayland session**, for the first exit criterion and for Task 6. The
  easiest way is a VM: install **GNOME Boxes** (`sudo apt install gnome-boxes`) and boot
  the **Fedora KDE Plasma Desktop** live ISO. It runs Wayland by default and has the
  `GlobalShortcuts` portal. About 3 GB of download and 20 min of setup. Run the spike
  scripts there once (Task 1's KDE column), then the Task 3–6 checks.
- **X11 once per merged task** ("Ubuntu on Xorg"), to check nothing regressed.
- **A second monitor or a different scale**, for Q4 / Q6 / Q7 and the multi-monitor crop.
  This machine has one 100 % screen.
- **Starting Kami as Kami** (Task 7): install the desktop file, and check which app the
  screenshot dialog names.
- Optional: Fedora Workstation (GNOME 48+) in the same VM tool, to see the
  `GlobalShortcuts` path on GNOME too. Sway or Hyprland only if you use one.
- A little OpenRouter credit (well under $0.10).

## Open questions

### Answered by the spike (2026-10-12)

1. **Does GNOME 46 ask permission for a non-interactive screenshot from an unsandboxed
   app, and does it remember?** Yes, once, and it remembers. But it remembers **per
   launching app**, taken from the systemd scope (the grant was stored for
   `com.microsoft.VSCode`). So starting Kami another way can ask again. Task 7 ships
   `org.kami.Kami.desktop` and documents starting Kami in an `app-org.kami.Kami-*` scope
   for one stable grant. The Deny response code is still a hand check.
2. **Does KDE need an app id for `GlobalShortcuts`?** Still open: it's the KDE run of
   `shortcut.py` with and without `--register` (needs you). There's no `Registry` on
   xdg-desktop-portal 1.18.4. The plan builds without registering. If KDE refuses, a
   Plan change adds registration to Task 6.
3. **Is on-screen drawing possible on GNOME Wayland?** Not with a full-screen layer on
   GNOME 46: the layer is opaque black outside the drawing, and it takes focus.
   GNOME gets in-panel doodles, and `ON_SCREEN_DESKTOPS` stays empty.

### Still open

4. **How do you start Kami day to day?** From a terminal, VS Code, the app grid, or a
   systemd user service? The screenshot grant follows whatever starts it (Q2). Task 7's
   docs cover the app grid (with the desktop file) and `systemd-run --scope`. If you use
   a systemd user service, its unit name decides the app id. That way isn't measured
   yet, so the plan doesn't claim anything about it. Tell Claude, and the README will
   cover your way.

## Closing the phase

When both exit criteria are ticked: bump the version to `0.4.0` in
`src/kami/__init__.py` and `pyproject.toml` (own PR: `bump version to 0.4.0`), tag
`v0.4.0`, and set Phase 3 to ✅ in [MILESTONES.md](../../MILESTONES.md). The version is
still `0.1.0` today. If the `0.2.0` and `0.3.0` bumps haven't happened by then, do them
first, in order.
