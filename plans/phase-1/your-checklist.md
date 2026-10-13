# Phase 1: your checklist

Tasks 1–7 are coded, merged, and CI is green on `main`. What's left are the steps only
you can do: things that need your API key, your desktop, or your GitHub account.
Tick each box when it's done.

Back to: [Phase 1 plan](README.md) · [Task recaps](../task-recaps.md) · [Milestones](../../MILESTONES.md)

---

## 1. Get `kami` running with your key

- [X] **Load your API key into the terminal.** Kami doesn't read `.env` by itself.
  Load it first:
  ``bash cd ~/Downloads/kami-scaffold source .venv-1/bin/activate set -a; source .env; set +a ``
  Don't have a key yet? Create one at [https://openrouter.ai/settings/keys](https://openrouter.ai/settings/keys).
  Make sure the account has credit: [https://openrouter.ai/settings/credits](https://openrouter.ai/settings/credits).
  Template: [.env.example](../../.env.example)
- [X] **Check your config uses `https://`.** If `base_url` in
  `~/.config/kami/config.toml` starts with `http://` and isn't a local model,
  Kami won't start. ([Task 4 recap](../task-recaps.md#phase-1--task-4-config-validation))
- [X] **Run the health check:**
  ``bash kami doctor ``
  The "API key" row should be ✓. The hotkey row is ✗ on Wayland, and that's
  expected (see step 2). ([Task 7 plan](task-7-version-doctor.md))

## 2. Hotkey on Wayland (GNOME)

On Wayland, apps can't grab global keys, so you add a desktop shortcut yourself.

- [X] Open **Settings → Keyboard → View and Customize Shortcuts → Custom Shortcuts → +**
  - Name: `Kami`
  - Command: `/home/nathan/Downloads/kami-scaffold/.venv-1/bin/kami toggle`
  - Shortcut: e.g. <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>K</kbd>

  GNOME guide: [https://help.gnome.org/users/gnome-help/stable/keyboard-shortcuts-set.html](https://help.gnome.org/users/gnome-help/stable/keyboard-shortcuts-set.html)
- [X] Start `kami` from the terminal in step 1, press the shortcut, and check that the panel shows and hides.

README section: [Hotkey: X11 vs Wayland](../../README.md#hotkey-x11-vs-wayland)

## 3. Manual checks from the task plans

I couldn't do these myself because they need your key, your credit, or your screen.

### Task 3: plain-language AI errors ([plan](task-3-llm-errors.md#manual-check))

- [X] **Wrong key:** `OPENROUTER_API_KEY=wrong kami`, ask anything. The panel says the key was "rejected".
- [X] **No internet:** turn Wi-Fi off and ask anything. The panel says it "can't reach" the server.
- [X] **Text-only model:** set `model` to a model without image input
  (browse [https://openrouter.ai/models](https://openrouter.ai/models)), then use Explain screen. The panel should say
  the model "can't read images". This costs close to nothing.

### Task 4: config validation ([plan](task-4-config-validation.md#manual-check))

- [X] Break the TOML on purpose (e.g. delete a `]`) and run `kami`. You should see a dialog
  naming the file and line, with no traceback. Undo the change afterwards.

### Task 5: logging ([plan](task-5-logging.md#manual-check))

- [X] Run `kami`, ask a question, and explain a region. Then:
  ``bash cat ~/.local/state/kami/kami.log grep -c -E "sk-|base64" ~/.local/state/kami/kami.log   # should print 0 ``
  The log should show events and durations, but no prompt, reply, key, or image data.

### Task 7: `kami doctor` ([plan](task-7-version-doctor.md#manual-check))

- [X] Over SSH (or a TTY with <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>F3</kbd>), with no display:
  `kami --version` and `kami doctor` both work.
- [X] Check that the report matches your machine: the hotkey and screen-capture rows
  say what actually happens on Wayland (and on X11, if you can log into an X11 session).
- [X] Look at the "Model … images:" row. Does it say the right thing for a vision model
  and for a text-only model?

## 4. GitHub settings (optional, recommended)

- [X] **Protect `main` so a red CI blocks merges.** Right now `main` is not protected.
  [https://github.com/nay-min-soe/kami/settings/branches](https://github.com/nay-min-soe/kami/settings/branches) → *Add branch ruleset* (or
  *Add classic rule*) for `main` → require status checks `test (3.11)` and `test (3.12)`.
  Docs: [https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
  ([Task 1 &#34;Done when&#34;](task-1-ci.md#done-when))
- [X] Look over the CI runs once: [https://github.com/nay-min-soe/kami/actions](https://github.com/nay-min-soe/kami/actions)

## 5. Close out Phase 1

- [X] **Commit the open edit** to [plans/phase-1/README.md](README.md) (the line about
  `/task-recap`). It's sitting uncommitted on `main`.
- [X] **Tick the exit criteria** in [plans/phase-1/README.md](README.md#phase-exit-criteria)
  and the Phase 1 boxes in [MILESTONES.md](../../MILESTONES.md#phase-1--foundation-hardening-v02),
  then set the Phase 1 status to ✅ in the table.
  - [ ] CI is green on every push to `main` (it is: last 3 runs passed)
  - [ ] Every LLM / config error shows a one-line human message (confirmed by section 3)
  - [ ] `kami doctor` explains why the hotkey or capture won't work (confirmed by section 3)
- [X] **Bump the version to `0.2.0`.** Today it's still `0.1.0` in two places:
  [`src/kami/__init__.py`](../../src/kami/__init__.py) and [`pyproject.toml`](../../pyproject.toml).
  Ask Claude to do this as its own PR (`bump version to 0.2.0`).
- [X] **Tag and publish the v0.2 release:** [https://github.com/nay-min-soe/kami/releases/new](https://github.com/nay-min-soe/kami/releases/new)
  (tag `v0.2.0`; use the [task recaps](../task-recaps.md) as release notes).
- [X] Clear the finished items in the "Waiting on you" list in [task-recaps.md](../task-recaps.md#waiting-on-you).

---

## Merged PRs, for reference

| Task                                       | PR                                                |
| ------------------------------------------ | ------------------------------------------------- |
| 1 · CI with pytest                        | [#1](https://github.com/nay-min-soe/kami/pull/1)   |
| 2 · Linting with ruff                     | [#6](https://github.com/nay-min-soe/kami/pull/6)   |
| 3 · Plain-language LLM errors             | [#9](https://github.com/nay-min-soe/kami/pull/9)   |
| 4 · Config validation                     | [#7](https://github.com/nay-min-soe/kami/pull/7)   |
| 5 · Logging                               | [#10](https://github.com/nay-min-soe/kami/pull/10) |
| 6 · Tests for app control and meetings    | [#8](https://github.com/nay-min-soe/kami/pull/8)   |
| 7 ·`kami --version` and `kami doctor` | [#11](https://github.com/nay-min-soe/kami/pull/11) |

Next up after this: [Phase 2: Explain screen v1 + better Ask](../../MILESTONES.md#phase-2--explain-screen-v1--better-ask-v03)
