# Phase 3: your checklist (getting ready)

The agents build Phase 3 on this machine. They can run commands and read pixels from
screenshots, but they can't click, drag, press keys, or log into another desktop. This
page lists what only you can do, in the order you'll need it. Tick each box as you go.

`/my-checklist 3` extends this page with the hand checks for Tasks 3–7 once they're
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

## 2. Answer the screenshot permission dialog once ✅

- [x] Done on 2026-10-12, during the spike: someone at the machine clicked **Allow**.
  GNOME stored the grant for `com.microsoft.VSCode`, the app that started the spike, not
  for Kami (Task 1, Q2). Builders' calls are silent now. **Keep that grant**: if section
  5's Deny test removes it, allow it again at the end, or builders' live checks will
  wait on a dialog.

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
   `git clone https://github.com/nay-min-soe/kami && cd kami && git checkout phase-3-wayland`
   (the spike scripts are in commit `0bd5417` there; if that branch isn't on GitHub yet,
   ask Claude to push it).
2. [ ] Install `uv` if it's missing: `curl -LsSf https://astral.sh/uv/install.sh | sh`,
   then open a new Konsole.
3. [ ] Run each KDE command from Task 1's
   [How to rerun](task-1-wayland-spike.md#how-to-rerun), in order. On the VM they start
   with `uv run --no-project --with PySide6 --with jeepney python -I` (there's no `.venv-1` there).
   Click whatever dialogs KDE shows.
4. [ ] For the hotkey row (Q8): run `shortcut.py`, accept KDE's dialog, then run
   `shortcut.py --register`. Each time, open System Settings → Shortcuts and note which
   app the binding is listed under.
5. [ ] Paste the printed lines to Claude: *"here are the KDE spike results"*. Claude
   fills in the KDE column.

## 5. Your hand checks on this machine (the spike's "needs you" rows)

The exact commands are in [How to rerun](task-1-wayland-spike.md#how-to-rerun). Run them
in a terminal in `~/Downloads/kami-scaffold`.

1. [ ] **Clicks pass through** (Q5): run `layer_probe.py --hold 10`. **The screen goes
   black except a magenta square for 10 s.** That's the finding, not a fault. Click a
   window under it: does the click reach it? It closes by itself.
2. [ ] **Deny** (Q2): remove the VS Code grant with the `DeletePermission` command in How
   to rerun. Run `portal_shot.py --timeout 60`, click **Deny**, and note the printed
   `response` number.
3. [ ] **From a plain Terminal** (Q2): open **Terminal** (not VS Code) and run
   `portal_shot.py --timeout 60`. Does a dialog appear, and which app does it name?
   Click **Allow**.
4. [ ] **Restore the builders' grant**: run `portal_shot.py --timeout 60` once from a VS
   Code terminal, and click **Allow** if a dialog appears.
5. [ ] **The desktop's picker** (Q11): run `portal_shot.py --interactive --timeout 120
   --layout`, pick an area, and note the printed `image WxH`.
6. [ ] **Leftovers** (Q3): after a run, open **Files** → **Pictures** (the file lands
   there, not in Screenshots), and the notification list (click the clock at the top).
   There should be no new screenshot and no notification with a thumbnail. Paste into
   Text Editor: no image.
7. [ ] Tell Claude the results.

## 6. Start Kami as Kami (10 min, after Task 7)

Your daily Kami is the systemd user service `kami.service`. That name gives the portal
no app id, so the screenshot permission can't be filed under Kami (Task 1, Q2). This is
**unmeasured** until you tick it.

1. [ ] Put `kami` on the session PATH:
   `ln -s ~/Downloads/kami-scaffold/.venv-1/bin/kami ~/.local/bin/kami`.
2. [ ] Rename the service:

   ```bash
   systemctl --user disable --now kami.service
   mv ~/.config/systemd/user/kami.service ~/.config/systemd/user/app-org.kami.Kami.service
   systemctl --user daemon-reload
   systemctl --user enable --now app-org.kami.Kami.service
   ```

3. [ ] Do one **Explain screen** capture, and answer the dialog if one appears.
4. [ ] Run
   `gdbus call --session --dest org.freedesktop.impl.portal.PermissionStore --object-path /org/freedesktop/impl/portal/PermissionStore --method org.freedesktop.impl.portal.PermissionStore.Lookup screenshot screenshot`.
   It should show `org.kami.Kami`. Tell Claude exactly what it printed.
5. [ ] The app-grid and terminal ways are in Task 7's Manual check, if you want to
   compare. For a GNOME custom shortcut, use
   `sh -c 'exec systemd-run --user --scope --unit=app-org.kami.Kami-$$ kami'`. The bare
   `systemd-run … $$ …` works only in a terminal.

## 7. Once per merged task: X11 check (10 min each)

Builders can't log into X11, so you check after each Phase 3 task is merged that nothing
broke there.

1. [ ] Log out (top-right menu → Power → Log Out). Click your name, then the gear icon,
   and pick **Ubuntu on Xorg**.
2. [ ] If your Kami service is running, stop it first (`systemctl --user stop
   app-org.kami.Kami.service`, or `kami.service` before section 6). Then, in a terminal
   in `~/Downloads/kami-scaffold`, run `KAMI_DEBUG_DOODLES=1 .venv-1/bin/kami`, open
   [the calibration page](../phase-2/calibration-target.html) in Firefox, then
   **Explain screen** → drag around the target. The corner circles sit on the corners
   (≤ 3 px).
3. [ ] Press your hotkey (<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>K</kbd>): the panel
   toggles.
4. [ ] Log back into the normal **Ubuntu** session.
