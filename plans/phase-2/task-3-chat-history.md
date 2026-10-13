# Task 3 — Chat history for Ask + "New chat"

**Size:** M · **Depends on:** — · **Branch:** `chat-history`

## Goal

Ask remembers the conversation, so "and in Python?" makes sense after a question about
sorting. **New chat** starts over.

## Current state

- `overlay.ask()` calls `client.ask(prompt)`. Every question is a fresh, one-message request.
- The output box shows only the latest answer, and the input keeps the old question text.
- Nothing stops a second question while the first is still running. Whichever reply
  arrives last wins, even if it belongs to the older question.

## Design

A new core module, `src/kami/conversation.py` (no Qt), owns the history. The panel
only displays it.

```python
@dataclass
class Turn:
    role: str                    # "user" | "assistant"
    text: str
    image: bytes | None = None   # used by Task 4

class Conversation:
    def __init__(self, system: str | None = None,
                 max_turns: int = 20, max_chars: int = 24_000) -> None: ...
    def messages_with(self, question: str) -> list[dict]: ...  # history + pending question, trimmed
    def record(self, question: str, answer: str) -> None: ...   # only on success
    def clear(self) -> None: ...
    @property
    def turns(self) -> list[Turn]: ...
```

- **Nothing changes on failure.** `messages_with` builds the request without changing
  the history. `record` adds the user + assistant pair only when the reply arrives.
  A failed or abandoned question leaves no half-finished turn behind.
- **Trimming:** drop the oldest user/assistant *pairs* until the history is within
  `max_turns` and `max_chars`. Never split a pair, and always keep the new question.
  These are constants, not config keys (smallest version first).
- `LLMClient` doesn't change: `client.chat(conversation.messages_with(q))`.
- **Stale replies:** the panel keeps `self._generation: int` and bumps it on New chat.
  A callback whose generation is out of date is dropped. While a request is running,
  the input is disabled, so only one question can be in flight.
- **Display:** the output shows the whole chat as Markdown (`**You:** ...` /
  `**Kami:** ...`), scrolled to the bottom. The input clears after sending.
- **Lifetime:** history lives in memory. Hiding the panel keeps it, New chat clears
  it, quitting forgets it. Nothing is written to disk.
- **Meeting notes** stays one-shot and doesn't touch the chat history.
- **Logging:** one INFO line per request with the turn count and character total,
  never the text.

## Files

| File | Change |
|---|---|
| `src/kami/conversation.py` | new |
| `src/kami/ui/overlay.py` | holds a `Conversation`, New chat button, generation guard, transcript view |
| `tests/test_conversation.py` | new |
| `README.md`, `ARCHITECTURE.md` | Ask now keeps history; new `conversation.py` box |

## Tests — `tests/test_conversation.py`

- [x] `test_first_question_has_system_and_user`: `messages_with("hi")` gives system + one user message
- [x] `test_record_adds_pair`: after `record`, the next `messages_with` contains both earlier messages in order
- [x] `test_messages_with_does_not_mutate`: calling it twice without `record` leaves `turns` empty
- [x] `test_no_system_when_none`: `Conversation(system=None)` sends no system message
- [x] `test_trims_oldest_pairs_by_turns`: `max_turns=4` with 5 recorded pairs keeps only the last pairs, never half a pair
- [x] `test_trims_by_chars_keeps_new_question`: one huge old answer is dropped, and the new question is always present
- [x] `test_clear_empties_history`
- [x] `test_works_with_fake_llm`: extend `FakeLLM` in `conftest.py` with `chat(messages)` that records the messages; one ask → record → second ask sends 3 messages (+ system)

## Manual check

- [ ] Ask "what's a Python list?", then "and a tuple?": the second answer compares to lists
- [ ] Click **New chat**, then ask "and a tuple?": the answer doesn't mention the earlier chat
- [ ] Ask something, click **New chat** before it answers: the late reply doesn't appear
- [ ] Hide and show the panel: the chat is still there
- [ ] `grep -c "tuple" ~/.local/state/kami/kami.log` prints 0

## Done when

- [x] Ask keeps a short history; New chat clears it
- [x] A late reply can never land in the wrong chat
- [x] `/security-check` run on the diff (chat text must not reach the log)

## Commits

1. `add conversation history model`
2. `keep chat history in ask with new chat button`
