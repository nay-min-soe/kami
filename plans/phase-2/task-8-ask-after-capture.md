# Task 8 — Type your question after the capture

**Size:** S · **Depends on:** Task 4 · **Branch:** `ask-after-capture`

## Goal

After dragging a box, Kami waits for your question instead of explaining straight
away. Pressing Enter on an empty input still gives the general explanation. Voice
input for this comes in Phase 6.

## Why

Explaining automatically answers a question you may not have. "Why does the line drop
in March?" gets a better answer (and better doodles) than a general explanation.

## Design

- After a successful capture, the panel holds `(png, region, screen)` and starts a fresh
  chat. Nothing is sent. The line above the input says "📷 Screen captured · type your
  question, or press Enter to explain it".
- Enter sends the picture + question with the JSON prompt (`learning.explain_region(client,
  png, question)`), so this first answer can draw doodles (decision 2: only the first answer
  draws). An empty question uses `USER_PROMPT` (`learning.first_question`).
- The answer becomes the start of the follow-up chat
  (`follow_up_conversation(png, lesson, question)`); follow-ups stay text-only and stream.
- Failure keeps the capture held and puts the question back, so Enter retries.
- New chat or another capture drops the held screenshot. Starting a capture clears old
  doodles, so they don't appear in the new screenshot.
- `KAMI_DEBUG_DOODLES=1` still draws the test pattern straight after the drag.
- Logging: `capture ready bytes=N` and `capture question chars=N`, never the text or image.
- Known limit: the doodles go where the box was. If you scroll while typing, they land
  on the old position.

## Tests

- [x] `test_explain_region_sends_the_users_question`
- [x] `test_empty_question_means_explain` (empty / spaces / newline)
- [x] `test_follow_up_conversation_starts_with_the_question`

## Manual check

See section 5, **Task 8**, in [your-checklist.md](your-checklist.md).

## Commits

1. `let the first capture question come from the user`
2. `wait for a typed question after capturing the screen`
