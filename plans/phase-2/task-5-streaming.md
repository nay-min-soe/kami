# Task 5 — Streaming replies

**Size:** M · **Depends on:** Task 3 · **Branch:** `streaming`

## Goal

Answers appear word by word as the model writes them, and a **Stop** button ends a
long answer early.

## Current state

- `LLMClient._request` waits for the whole JSON body.
- `ui/worker.py` signals only `done` and `failed`, so there is no way to send partial text.
- A long answer means several seconds of "_Thinking..._".

## What OpenRouter sends (checked 2026-10-08, <https://openrouter.ai/docs/api-reference/streaming>)

- Server-Sent Events: lines `data: {json}`, each with `choices[0].delta.content`;
  the stream ends with `data: [DONE]` (after a usage chunk with no content).
- Keep-alive comment lines, `: OPENROUTER PROCESSING`. Lines starting with `:` must be skipped.
- **Errors before streaming** are a normal HTTP error status with a JSON `error` body,
  so the existing `_error()` mapping applies.
- **Errors mid-stream** arrive with status 200 as
  `data: {"error": {"code": "server_error", "message": "..."}, "choices": [{"finish_reason": "error"}]}`.
  `code` is a string here, so `_error(200, error)` maps it to `server`, which is right.
- Closing the connection cancels generation (and billing) on providers that support it.
  Others keep running, so Stop saves money only on some models.

## Design

```python
def chat_stream(self, messages: list[dict], on_delta: Callable[[str], None],
                cancel: threading.Event | None = None) -> str:
    """Stream a reply, calling on_delta for each piece. Returns the full text."""
```

- Use `self.http.stream("POST", ..., json={..., "stream": True})`. Pull the headers
  out of `_request` into `_headers()` so both paths share them (and the key handling).
- Non-2xx: `response.read()`, then reuse the same JSON-error path → `_error(status, error)`.
- Read with `iter_lines()`: skip blank lines and `:` comments, stop at `[DONE]`,
  `json.loads` the rest, and raise via `_error` if there's an `error` key. Skip
  chunks with no `delta.content`.
- Between lines, if `cancel.is_set()`, close the response and raise
  `LLMError("cancelled", "Stopped.")`.
- The connection drops after some text → `network` error. The panel keeps the partial
  text and adds "_(cut off)_".
- The stream ends with no text at all → `bad_response`.
- Timeouts: httpx's read timeout applies **between** chunks, so a long but steady
  answer never times out. Keep 90 s.
- Logging: model, time to first token, total time, and the outcome kind. Never the text.

**Worker:** `run_in_background(..., on_progress=cb)` adds `progress = Signal(str)` to
`_Signals` and passes `on_delta=self.signals.progress.emit` into `fn`. The signal crosses
threads, so Qt queues it onto the UI thread. `cancelled` errors are not shown as "Oops".

**Panel:**
- Ask and follow-ups stream. Explain screen's first answer is JSON, so it doesn't
  stream ("_Looking at your screen..._" stays). Meeting notes may stream too if it's a
  one-line change.
- Don't call `setMarkdown` on every token, because that gets slow on long answers.
  Collect pieces and repaint with a 50 ms `QTimer` while streaming.
- A **Stop** button shows while streaming. It sets the `cancel` event, and the partial
  answer is kept and recorded in the chat with a "_(stopped)_" note.
- New chat during a stream: set `cancel` *and* bump the generation (Task 3), so
  nothing late lands in the new chat.
- Copy (Task 2) stays disabled until the stream finishes.

## Files

| File | Change |
|---|---|
| `src/kami/llm/client.py` | `chat_stream`, `_headers`, SSE parsing |
| `src/kami/ui/worker.py` | `progress` signal, `on_progress` |
| `src/kami/ui/overlay.py` | streaming render, Stop button |
| `tests/test_llm_client.py` | streaming cases with `MockTransport` |
| `README.md`, `ARCHITECTURE.md` | replies stream; Stop |

## Tests — add to `tests/test_llm_client.py`

Build SSE bodies as bytes, e.g. `b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\ndata: [DONE]\n\n'`,
returned by a `MockTransport` handler with `content-type: text/event-stream`.

- [x] `test_stream_yields_deltas_in_order`: `on_delta` gets `["Hel", "lo"]` and the return value is `"Hello"`
- [x] `test_stream_sends_stream_true`: the request JSON has `"stream": true`
- [x] `test_stream_skips_comments_and_blank_lines`: `: OPENROUTER PROCESSING` lines are ignored
- [x] `test_stream_skips_chunks_without_content`: role-only and usage chunks are skipped
- [x] `test_stream_http_error_maps_to_kind`: 401 / 402 / 429 before streaming → `auth` / `credits` / `rate_limit`
- [x] `test_stream_mid_error_maps_to_server`: the mid-stream error event above raises `LLMError` with kind `server`, after the earlier deltas were delivered
- [x] `test_stream_cancel_stops_reading`: set `cancel` inside `on_delta` after the first piece; raises `cancelled`, and no later delta arrives
- [x] `test_stream_empty_is_bad_response`: only `[DONE]` → `bad_response`
- [x] `test_stream_error_never_contains_api_key`: same check as the Phase 1 non-stream test

## Manual check

- [ ] Ask for "a 300-word story": text appears progressively and the panel stays responsive
- [ ] Click **Stop** halfway: the text stops, the partial answer stays, and the next question works
- [ ] Wrong key: the same "rejected" sentence as before, no partial text
- [ ] The log shows time to first token, with no story text

## Done when

- [x] Ask and follow-up replies stream
- [x] Every Phase 1 error kind still shows its plain sentence when streaming
- [x] `/security-check` run on the diff

## Commits

1. `add streaming chat to llm client`
2. `stream replies into the panel`
