# Task 2 — Copy-to-clipboard button

**Size:** S · **Depends on:** — · **Branch:** `copy-answer`

## Goal

One click copies Kami's last answer, so it can be pasted into an editor, chat or notes.

## Current state

- `overlay._say(text)` calls `self.output.setMarkdown(text)` and keeps nothing else.
  Selecting text in the `QTextBrowser` works, but it copies rendered text and is fiddly.
- Status lines ("_Thinking..._") and errors ("**Oops:** ...") use the same `_say`.

## Design

- Keep the last real answer as Markdown source in `self._answer: str`. Set it only when
  an answer arrives, never for status or error lines.
- A **Copy** button next to the output. It copies `self._answer` with
  `QGuiApplication.clipboard().setText(...)`, so pasting keeps the Markdown
  (`**bold**`, lists, code fences). The label shows "Copied ✓" for 1.5 s.
- The button is disabled while there is no answer or a request is running.
- After Task 3, "answer" means the latest assistant reply, not the whole chat.

## Files

| File | Change |
|---|---|
| `src/kami/ui/overlay.py` | `_answer`, Copy button, enable/disable |
| `README.md` | mention Copy in the "What it does" table (Ask row) |

No core logic changes, so there's no new pytest test.

## Manual check

- [ ] Ask something that gets a list or code in the reply, click **Copy**, and paste
      into a text editor: you get the Markdown source
- [x] While "_Thinking..._" shows, Copy is disabled (offscreen test)
- [x] After an error, Copy still copies the previous answer (or is disabled if there is none)
- [ ] Copy, then hide the panel with Esc, then paste: it still works (X11 keeps the
      clipboard while Kami runs)

## Done when

- [x] The last answer can be copied in one click
- [x] Status and error lines are never what gets copied

## Commit

`add copy button for answers`
