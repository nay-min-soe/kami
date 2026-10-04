---
name: explain-first
description: Plain-English brief of possible outcomes and risks, shown before writing or editing any code in Kami. Use before every code change, refactor, dependency change, or file deletion in this repo.
---

# Explain first

Kami's own rule is *never act blind*: before a sensitive action it shows what it wants to do and what could go wrong, and waits for **Do it**. Hold yourself to the same rule before touching code.

## Steps

1. **Look before you talk.** Read every file you plan to change and the tests that cover it (`tests/`). The brief is built on what the code actually does now.
2. **Write the brief** in plain English, as if to a smart friend who doesn't read Python. Short sentences, everyday words; name a technical term only once, with a few-word gloss in brackets.

   ```
   ### What I want to do
   One or two sentences. Which files, and what changes for the user of Kami.

   ### If it goes right
   What the user will see or be able to do afterwards.

   ### What could go wrong
   - <risk> — how likely (low / medium / high) — what I'll do to prevent or catch it
   (2–5 risks, most serious first)

   ### How to undo it
   e.g. "Nothing is committed; `git restore <file>` puts it back", or "run /backup first".

   ### Your call
   Do it / Change the plan / Nope
   ```

3. **Wait** for the user's answer, then do only what they approved. A changed plan gets a new, shorter brief.

The brief is done when every file you will touch is named and every risk has a likelihood and a guard.

## Risks to check for in Kami

Go through these so the risk list is real, not generic:

- **Safety gate**: could this let an app-control action skip `kami.safety.gate`, the allowlist, or the "Nope" default? If yes, it is high risk; say so plainly and suggest the `security-check` skill.
- **Frozen UI**: a slow call (LLM request, file or audio work) on the Qt main thread freezes the panel. Blocking work belongs in `kami.ui.worker.run_in_background`.
- **X11 vs Wayland**: hotkeys and screen capture behave differently; say which one the change was reasoned about.
- **Privacy**: anything that sends screenshots, transcripts, or text to the LLM provider, or stores them on disk.
- **Config**: renaming or removing a key in `config.example.toml` breaks users' existing `~/.config/kami/config.toml`.
- **Tests**: which tests cover this, and whether `uvx pytest -q` can prove it works. UI changes usually can't be tested automatically; say the user will need to try it by hand.
- **Size**: a change touching more than ~3 files, or adding a dependency, deserves a `/backup` first.

## Small changes

For a typo, comment, or one-line fix, the brief collapses to two lines: what changes, and the one thing that could go wrong. Still wait for the go-ahead.
