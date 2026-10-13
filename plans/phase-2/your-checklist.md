# Phase 2: your checklist

Tasks 1–7 are coded, tested by me where a computer can test them, pushed, and each has
a PR with green CI. What's left are the steps only you can do: merging on GitHub,
logging into an X11 session, looking at the screen, and spending a few cents of
OpenRouter credit. Tick each box as you go.

Back to: [Phase 2 plan](README.md) · [Task recaps](../task-recaps.md) · [Milestones](../../MILESTONES.md)

**Time needed:** about 1 hour for sections 1–5, plus 30–60 min for the monitor tests
in section 6. **Cost:** well under $0.10 of OpenRouter credit.

## Tools you'll use

| Tool | What for | How to open it |
|---|---|---|
| Web browser | GitHub (merging PRs, releases) and test pages | Firefox from the dock |
| Terminal | starting Kami, `git`, reading the log | <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>T</kbd> |
| GNOME login screen | switching to the X11 session | log out: top-right menu → Power → Log Out |
| GNOME Screenshot | taking pictures of the doodles | <kbd>Print Screen</kbd> key; saved to `~/Pictures/Screenshots/` |
| GNOME magnifier | dragging exactly onto a corner | toggle on/off with <kbd>Super</kbd>+<kbd>Alt</kbd>+<kbd>8</kbd> (zoom level: Settings → Accessibility → Zoom) |
| GIMP (install once) | measuring offsets in pixels | `sudo apt install gimp` |
| Text Editor | pasting copied answers | "Text Editor" in the app grid |
| `xrandr` (already installed) | listing monitors, making virtual ones | terminal |

---

## 1. Phase 1 leftovers (5 min, do these first)

Your Phase 1 checklist has these ticked, but the repo shows they didn't happen: the
version is still `0.1.0` in [`src/kami/__init__.py`](../../src/kami/__init__.py) and
[`pyproject.toml`](../../pyproject.toml), and there's no `v0.2.0` tag.

- [ ] Ask Claude: *"open a PR that bumps the version to 0.2.0"*. Merge it **before** the
      Phase 2 PRs. It touches only those two files, so it won't conflict with them.
- [ ] Tag the release: open <https://github.com/nay-min-soe/kami/releases/new>, type
      `v0.2.0` in **Choose a tag** → **Create new tag**, target `main`, title `v0.2.0`.
      For the notes, paste the Phase 1 entries from [task-recaps.md](../task-recaps.md),
      then click **Publish release**.
- [ ] In [MILESTONES.md](../../MILESTONES.md), tick the Phase 1 boxes and set Phase 1 to ✅
      in the table.

## 2. Merge the PRs, in this order (15 min)

The PRs are **stacked**: each one builds on the one before. Until the earlier ones
are merged, a PR also shows their commits. That's expected, and the diff shrinks
by itself as you merge.

| Order | PR | What |
|---|---|---|
| 1 | [#12](https://github.com/nay-min-soe/kami/pull/12) | Task 1: safe annotation parsing, only http(s) links open |
| 2 | [#13](https://github.com/nay-min-soe/kami/pull/13) | Clear message when screen capture fails (your "error 400") |
| 3 | [#14](https://github.com/nay-min-soe/kami/pull/14) | Task 2: Copy button |
| 4 | [#15](https://github.com/nay-min-soe/kami/pull/15) | Task 3: chat history + New chat |
| 5 | [#16](https://github.com/nay-min-soe/kami/pull/16) | Task 4: follow-up questions about the capture |
| 6 | [#17](https://github.com/nay-min-soe/kami/pull/17) | Task 5: streaming replies + Stop |
| 7 | [#18](https://github.com/nay-min-soe/kami/pull/18) | Task 6: multi-monitor, HiDPI, calibration mode |
| 8 | [#19](https://github.com/nay-min-soe/kami/pull/19) | Task 7: fade, 📌 Keep, labels that stay on screen |
| 9 | [#20](https://github.com/nay-min-soe/kami/pull/20) | Task 8: type your question after the capture |

For each PR, in order:

- [ ] Open it. At the bottom, check that **test (3.11)** and **test (3.12)** are green ✓.
      (Red? Click **Details** to see which test failed, then tell Claude the PR number.)
- [ ] Click **Merge pull request** → **Create a merge commit** (the same kind as your
      earlier PRs) → **Confirm merge**. If GitHub offers **Delete branch**, that's fine.
- [ ] Wait for the next PR's checks to rerun and go green before merging it.

GitHub says **"This branch has conflicts"**? Something was merged out of order. Don't
click "Resolve conflicts". Tell Claude *"PR #N has conflicts, rebase it on main"*.

When all 8 are merged, update your copy:

```bash
cd ~/Downloads/kami-scaffold
git checkout main
git pull
```

- [ ] `git log --oneline -3` shows the merge of #19 on top.

**Two files have uncommitted changes from you:** a `.venv-1` line in `README.md`, and
the plan edits (`MILESTONES.md`, `plans/phase-1/*`, `plans/phase-2/`). `git checkout`
keeps them. When you're ready, ask Claude *"open a PR with the phase 2 plan files"*.

## 3. Switch to an X11 session (5 min)

Explain screen can't capture on Wayland yet (that's Phase 3). Since #13 you get a clear
message instead of "error 400", but for the tests below you need X11. Ubuntu 24.04
still includes it.

- [ ] Save your work, then log out (top-right menu → Power → **Log Out**).
- [ ] On the login screen, click your name. Before typing the password, click the
      **gear icon ⚙** at the bottom right and pick **"Ubuntu on Xorg"**. Then log in.
- [ ] Check in a terminal: `echo $XDG_SESSION_TYPE` prints `x11`.
- [ ] The choice is remembered. To go back later, pick **"Ubuntu"** under the gear.

## 4. Start Kami for testing

Do this in every new terminal:

```bash
cd ~/Downloads/kami-scaffold
source .venv-1/bin/activate
set -a; source .env; set +a      # loads your OpenRouter key
kami doctor                      # every row ✓ (on X11 the hotkey and screen rows are ✓ too)
kami                             # starts Kami; leave this terminal open
```

- [ ] `kami doctor` shows ✓ for **Screen grab** and **Hotkey** on X11.
- [ ] **Avoid a double hotkey.** On X11, Kami listens for <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>K</kbd>
      itself, and your GNOME custom shortcut (made for Wayland) fires on the same keys.
      Both toggle the panel, so it opens and closes at once. While you're on X11, open
      Settings → Keyboard → View and Customize Shortcuts → Custom Shortcuts → **Kami**
      and change its shortcut to something else (e.g. <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>J</kbd>),
      or remove it. Put it back when you return to Wayland.
- [ ] Press <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>K</kbd>: the panel opens and stays open.
- [ ] `config.toml` has a vision model (`model = ...` in `~/.config/kami/config.toml`,
      e.g. one from <https://openrouter.ai/models?input_modalities=image>).

To stop Kami: tray icon → Quit, or <kbd>Ctrl</kbd>+<kbd>C</kbd> in its terminal.

## 5. Manual checks, task by task (30 min)

Each check links to its section in the task plan. Tick the box there too, so the plans
stay current.

### #13: capture message ([PR](https://github.com/nay-min-soe/kami/pull/13))

- [ ] **On Wayland** (before you switch, or later): Explain screen → drag a box. The panel
      says *"Kami couldn't capture your screen…"*, with no "error 400".
- [ ] **On X11:** Explain screen → drag a box around some text → press <kbd>Enter</kbd>
      in the empty input. You get an explanation and doodles.

### Task 1: safe parsing and links ([plan](task-1-annotation-parsing.md#manual-check))

- [ ] Open Text Editor and type: `Visit [click me](file:///etc/passwd) for details`.
      Explain screen → drag around that line → <kbd>Enter</kbd>. If Kami's answer contains a **click me**
      link, click it: **nothing opens**. Then in a terminal:
      `grep "blocked link" ~/.local/state/kami/kami.log` shows `scheme 'file'`.
      (If the model doesn't repeat the link, ask a follow-up: *"repeat that link exactly"*.)
- [ ] A normal Explain screen (drag, then <kbd>Enter</kbd>) still draws circles and arrows.

### Task 2: Copy button ([plan](task-2-copy-button.md#manual-check))

- [ ] Ask *"give me a 3-item list and a tiny python code block"*. Click **Copy**, then
      paste into Text Editor: you see the Markdown (`- item`, ```` ``` ```` fences).
- [ ] Click **Copy**, press <kbd>Esc</kbd> to hide the panel, then paste again: it still works.

### Task 3: chat history ([plan](task-3-chat-history.md#manual-check))

- [ ] Ask *"what's a Python list?"*, then *"and a tuple?"*: the second answer compares the two.
- [ ] Click **New chat**, then ask *"and a tuple?"*: no mention of lists.
- [ ] Ask something long, then click **New chat** right away: no reply appears later.
- [ ] Hide the panel (<kbd>Esc</kbd>) and summon it again: the chat is still there.
- [ ] `grep -c tuple ~/.local/state/kami/kami.log` prints `0` (no chat text in the log).

### Task 4: follow-ups ([plan](task-4-follow-ups.md#manual-check))

- [ ] Open a chart: in Firefox, search images for "bar chart example". Explain screen
      → drag around the chart → <kbd>Enter</kbd> (explanation + doodles). Then type
      *"which bar is highest?"*: the answer refers to
      the chart, with no new capture. The line above the input says
      **📷 Asking about your screen capture**.
- [ ] The follow-up draws **no new doodles**, and the first ones stay until they fade.
- [ ] **New chat**, then *"which bar is highest?"*: Kami says it can't see a chart.
- [ ] Do a second Explain screen on something else: follow-ups are now about that.
- [ ] `grep -c base64 ~/.local/state/kami/kami.log` prints `0`.

### Task 8: type your question after the capture ([plan](task-8-ask-after-capture.md#manual-check))

- [ ] Explain screen → drag a box. **Nothing is sent yet**: the panel says *"Screen
      captured. What do you want to know about it?"*, the line above the input says
      **📷 Screen captured · type your question…**, and the cursor is in the input.
- [ ] Type a real question about what you captured (e.g. on a chart: *"why does the
      line drop in March?"*) and press <kbd>Enter</kbd>. The answer is about **your
      question**, and the doodles mark what it talks about.
- [ ] Capture again and press <kbd>Enter</kbd> with the input **empty**: you get the
      usual general explanation.
- [ ] Capture, then click **New chat** before asking: the 📷 line disappears and your
      next question is a normal Ask (no picture).
- [ ] Turn Wi-Fi off, capture, ask: you get the "can't reach" message and your question
      is back in the input. Turn Wi-Fi on and press <kbd>Enter</kbd>: it works with no new capture.
- [ ] `grep -E "capture (ready|question)" ~/.local/state/kami/kami.log` shows sizes and
      counts only, never your question.

### Task 5: streaming ([plan](task-5-streaming.md#manual-check))

- [ ] Ask *"write a 300-word story about a ghost"*: text appears bit by bit, and you can
      move the panel while it streams.
- [ ] Ask again and click **Stop** halfway: the text stops and ends with *(stopped)*,
      and the next question works.
- [ ] Quit Kami and start it with a wrong key: `OPENROUTER_API_KEY=wrong kami`. Ask
      anything: the panel says the key was **rejected**, with no half answer. Quit, then
      start normally again.
- [ ] `grep first_token ~/.local/state/kami/kami.log` shows timings and no story text.

### Task 7: doodle polish ([plan](task-7-annotation-polish.md#manual-check))

Start Kami with the free test pattern: `KAMI_DEBUG_DOODLES=1 kami`. Explain screen then
draws fixed doodles and makes **no AI call**.

- [ ] At about 25 s the doodles **fade** over half a second instead of vanishing.
- [ ] Click **📌 Keep** (it turns pink), then Explain screen: the doodles stay past 25 s.
      **Clear doodles** still removes them. Click Keep again to turn it off.
- [ ] Drag a box in the **top-right corner** of the screen: every label is fully visible.
- [ ] Labels near each other don't overlap (the four corner labels of a small box).

## 6. Multi-monitor and HiDPI test matrix (Task 6; 30–60 min)

This proves the two Phase 2 exit criteria. You have one 1920×1080 laptop screen
(`eDP-1`). Most rows can be faked with a **virtual split** of that screen; the
"monitor left of the primary" row needs a real second monitor.

### 6a. Prepare

- [ ] Install GIMP: `sudo apt install gimp`
- [ ] Open the calibration page in Firefox:
      `firefox ~/Downloads/kami-scaffold/plans/phase-2/calibration-target.html`, and
      make sure zoom is 100% (<kbd>Ctrl</kbd>+<kbd>0</kbd>).
- [ ] Try the magnifier: <kbd>Super</kbd>+<kbd>Alt</kbd>+<kbd>8</kbd> turns it on and off.
      It follows the mouse.

### 6b. How to measure one row

1. Start Kami with the row's command (below), always with `KAMI_DEBUG_DOODLES=1`.
2. Explain screen → with the magnifier on, drag **from the centre of the top-left
   blue cross to the centre of the bottom-right blue cross**.
3. Within 25 s (or with **📌 Keep** on), press <kbd>Print Screen</kbd> → **Screen** → capture.
4. Open the screenshot in GIMP (`~/Pictures/Screenshots/`), zoom to 800% (key `4`),
   and hover the centre of a blue cross, then the centre of the pink circle on it.
   GIMP shows the pointer's x, y at the bottom-left. The offset is the larger of the
   x and y differences.
5. Check all four corners and the middle, and write the **worst** offset in the table.
6. Repeat with the page moved so the box touches a **screen edge**: drag the Firefox
   window so the red box is at the right or bottom edge. That's the "at screen edge" column.

Target: **≤ 3 px**. Each row is a fresh `kami` start. Quit the previous one first.

### 6c. The rows

| Row | Setup and command |
|---|---|
| 1 monitor, 100% | `KAMI_DEBUG_DOODLES=1 kami` |
| 1 monitor, 200% | `KAMI_DEBUG_DOODLES=1 QT_SCREEN_SCALE_FACTORS="eDP-1=2" kami` |
| 2 monitors, both 100% | make the virtual split (below), then `KAMI_DEBUG_DOODLES=1 kami`; test on **both** halves |
| 2 monitors, 100% + 200% | split, then `KAMI_DEBUG_DOODLES=1 QT_SCREEN_SCALE_FACTORS="KAMI-LEFT=1;KAMI-RIGHT=2" kami` |
| 2 monitors, 100% + 150% | split, then `KAMI_DEBUG_DOODLES=1 QT_SCREEN_SCALE_FACTORS="KAMI-LEFT=1;KAMI-RIGHT=1.5" kami` |
| Secondary **left of** primary | needs a real monitor: plug it in, Settings → **Displays**, drag it to the left of the laptop, set the laptop as **Primary**, Apply. Check `xrandr --listmonitors` shows a negative or left position. Then `KAMI_DEBUG_DOODLES=1 kami` and test on the left monitor |

**Virtual split** (makes Qt see two monitors, each 960×1080, on your one screen):

```bash
xrandr --setmonitor KAMI-LEFT  960/170x1080/190+0+0   eDP-1
xrandr --setmonitor KAMI-RIGHT 960/170x1080/190+960+0 none
xrandr --listmonitors            # shows KAMI-LEFT and KAMI-RIGHT
```

If `--listmonitors` doesn't show both, or GNOME resets them, tell Claude. You can then
use a real second monitor for these rows instead.

Undo it when you're done (or just log out):

```bash
xrandr --delmonitor KAMI-LEFT; xrandr --delmonitor KAMI-RIGHT
```

With the split on, also check:

- [ ] Move the mouse to the right half and summon the panel: it opens on the **right
      half**, not always the left one.

### 6d. Write down the results

- [ ] Fill in the offsets in the **Test matrix** table in
      [task-6-multi-monitor-hidpi.md](task-6-multi-monitor-hidpi.md#test-matrix-by-hand-x11-session-kami_debug_doodles1).
      No second monitor for the last row? Write "not tested: no second monitor".
- [ ] **Every offset ≤ 3 px?** Tick exit criteria 1 and 2 in the
      [Phase 2 README](README.md#phase-exit-criteria).
- [ ] **Any offset > 3 px?** Don't tick. Send Claude: the row, the offset and its
      direction ("circles are 12 px too far right"), whether it happens only at the edge,
      plus the output of `xrandr --listmonitors` and `kami doctor`. The likely fixes
      (the capture call at scaled screens, or telling the window manager not to move the
      doodle window) are known; they just need your numbers first.

## 7. Close Phase 2

- [ ] All three exit criteria ticked in [README.md](README.md#phase-exit-criteria):
  - [ ] Explain screen works on two monitors with different scaling (section 6)
  - [ ] Annotations land within a few pixels on every tested setup (section 6)
  - [ ] A follow-up about the same region needs no new capture (Task 4 checks)
- [ ] Ask Claude: *"open a PR that bumps the version to 0.3.0"*, and merge it.
- [ ] Release `v0.3.0`: <https://github.com/nay-min-soe/kami/releases/new> → tag
      `v0.3.0` on `main`; use the Phase 2 entries from [task-recaps.md](../task-recaps.md)
      as notes.
- [ ] In [MILESTONES.md](../../MILESTONES.md): tick the Phase 2 boxes and set Phase 2 to ✅.
- [ ] Tick the done items in "Waiting on you" at the top of [task-recaps.md](../task-recaps.md).

## If something goes wrong

| Problem | What to do |
|---|---|
| Kami won't start | Run `kami doctor` and read the ✗ rows. Config mistakes name the file, the key and the fix |
| "Oops: …" in the panel | The sentence says what failed. For more, `tail -50 ~/.local/state/kami/kami.log` |
| Explain screen shows the capture message on X11 | Check `echo $XDG_SESSION_TYPE` is `x11`, then send Claude the `kami doctor` output |
| Doodles in the wrong place | Use section 6 to measure, then send Claude the numbers |
| A PR's CI is red | Click **Details** on the failed check; tell Claude the PR number |
| More detail in the log | Start with `KAMI_LOG_LEVEL=DEBUG kami` |

The log never contains your key, screenshots, questions or answers, so it's safe to share.
