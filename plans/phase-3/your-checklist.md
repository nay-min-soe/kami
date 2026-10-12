# Phase 3: your checklist (getting ready)

The agents build Phase 3 on this machine. They can run commands and read pixels from
screenshots, but they can't click, drag, press keys, or log into another desktop. This
page lists what only you can do, in the order you'll need it. Tick each box as you go.

`/my-checklist 3` extends this page with the hand checks for Tasks 2–7 once they're
built. Until then, these are the steps that unblock the builders or take a while to set
up.

Back to: [Phase 3 plan](README.md) · [Task 1 findings](task-1-wayland-spike.md#findings) ·
[Milestones](../../MILESTONES.md)

**Time needed:** about 10 min now, plus about 30 min for the KDE VM (mostly download).
**Cost:** nothing yet.

## 1. Merge PR #20 (5 min)

Every Phase 3 branch is stacked on PR #20 (Phase 2 Task 8, "type your question after the
capture").

1. [ ] Open <https://github.com/nay-min-soe/kami/pull/20>. At the bottom, check that
   **test (3.11)** and **test (3.12)** are green ✓.
2. [ ] Click **Merge pull request** → **Create a merge commit** → **Confirm merge**.

## 2. Answer the screenshot permission dialog once (2 min, only if Task 1 asks)

Task 1's [Findings](task-1-wayland-spike.md#findings), row Q2, says whether GNOME showed
a permission dialog that a builder couldn't click.

1. [ ] Read row Q2. If it says "dialog appeared", go on. If not, skip this section.
2. [ ] Open a terminal (<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>T</kbd>) and run:

   ```bash
   cd ~/Downloads/kami-scaffold
   .venv-1/bin/python -I plans/phase-3/spike/portal_shot.py --timeout 60
   ```

3. [ ] A GNOME dialog asks whether to allow the screenshot. Click **Allow**. The
   terminal prints `response 0` and `deleted True`.
4. [ ] Run the same command again. Note whether the dialog comes back, and tell Claude:
   *"the screenshot dialog came back"* or *"it didn't come back"*.

## 3. Set up a KDE Plasma 6 Wayland VM (about 30 min)

You need this for the first exit criterion (Explain screen on KDE Wayland) and for Task 6
(KDE's own hotkey dialog).

1. [ ] Install GNOME Boxes: `sudo apt install gnome-boxes`.
2. [ ] Download the **Fedora KDE Plasma Desktop** live ISO (about 3 GB) from
   <https://fedoraproject.org/spins/kde/download>.
3. [ ] Open **Boxes** → **+** → **Install from File** → pick the ISO. Give it 4 GB of
   memory, then start it. It boots into Plasma on Wayland.
4. [ ] In the VM, open **Konsole** and check: `echo $XDG_SESSION_TYPE` prints `wayland`.
5. [ ] Leave the VM for now. Section 4 says what to run there once Task 1 is done.

## 4. Run the spike on KDE (15 min, after Task 1)

1. [ ] In the VM's Konsole, get the code:
   `git clone https://github.com/nay-min-soe/kami && cd kami && git checkout wayland-spike`
   (or the branch Task 1's PR names).
2. [ ] Install `uv` if it's missing: `curl -LsSf https://astral.sh/uv/install.sh | sh`,
   then open a new Konsole.
3. [ ] Run each KDE command from Task 1's
   [How to rerun](task-1-wayland-spike.md#how-to-rerun), in order. On the VM they start
   with `uv run --no-project --with PySide6 python -I` (there's no `.venv-1` there).
   Click whatever dialogs KDE shows.
4. [ ] For the hotkey row (Q8): run `shortcut.py`, accept KDE's dialog, then run
   `shortcut.py --register`. Each time, open System Settings → Shortcuts and note which
   app the binding is listed under.
5. [ ] Paste the printed lines to Claude: *"here are the KDE spike results"*. Claude
   fills in the KDE column.

## 5. Your hand checks on this machine (after Task 1)

These are the Task 1 rows marked "needs you" for GNOME. The exact commands are in
[How to rerun](task-1-wayland-spike.md#how-to-rerun).

1. [ ] **Clicks pass through** (Q5): while the magenta square shows, click a window
   under it. The click must reach that window.
2. [ ] **Deny** (Q2): run `portal_shot.py`, click **Deny** in the dialog, and note the
   printed `response` number.
3. [ ] **The desktop's picker** (Q11): run `portal_shot.py --interactive --timeout 120`,
   pick an area, and note the printed size.
4. [ ] **Leftovers** (Q3): after a run, open **Files** → **Pictures** → **Screenshots**,
   and the notification list (click the clock at the top). There should be no new shot
   from the spike. Paste into Text Editor: no image.
5. [ ] Tell Claude the four results.

## 6. Once per merged task: X11 check (10 min each)

Builders can't log into X11, so you check after each Phase 3 task is merged that nothing
broke there.

1. [ ] Log out (top-right menu → Power → Log Out). Click your name, then the gear icon,
   and pick **Ubuntu on Xorg**.
2. [ ] In a terminal in `~/Downloads/kami-scaffold`, run `KAMI_DEBUG_DOODLES=1 .venv-1/bin/kami`, open
   [the calibration page](../phase-2/calibration-target.html) in Firefox, then
   **Explain screen** → drag around the target. The corner circles sit on the corners
   (≤ 3 px).
3. [ ] Press your hotkey (<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>K</kbd>): the panel
   toggles.
4. [ ] Log back into the normal **Ubuntu** session.
