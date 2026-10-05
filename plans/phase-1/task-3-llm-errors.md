# Task 3 — Plain-language LLM errors

**Size:** M · **Depends on:** — · **Branch:** `llm-errors`

## Goal

When a model call fails, the panel shows one short sentence that says what went
wrong and what to do, not a raw `httpx` message.

## Current state

- `LLMClient.chat` calls `response.raise_for_status()` and indexes
  `response.json()["choices"][0]["message"]["content"]` directly.
- `ui/worker.py` turns any exception into `str(exc)`, so the user sees text like
  `Client error '401 Unauthorized' for url 'https://openrouter.ai/...'`.
- An odd response body raises `KeyError: 'choices'`, which tells the user nothing.
- `MissingAPIKey` is the only friendly error.

## Design

Add one exception type with a `kind` and a human `message`. The worker already
shows `str(exc)`, so the UI needs no change.

```python
class LLMError(RuntimeError):
    def __init__(self, kind: str, message: str) -> None: ...
```

| Situation | `kind` | Message (draft) |
|---|---|---|
| no key | `missing_key` | keep the current `MissingAPIKey` text (make it a subclass of `LLMError`) |
| 401 / 403 | `auth` | "Your API key was rejected. Check KAMI_API_KEY or OPENROUTER_API_KEY." |
| 402 | `credits` | "Your OpenRouter account is out of credit." |
| 429 | `rate_limit` | "Too many requests. Wait a minute and try again." |
| 5xx | `server` | "The model provider had an error. Try again shortly." |
| timeout | `timeout` | "The model took longer than 90 s to answer." |
| connect error | `network` | "Can't reach {host}. Check your internet connection or `base_url`." |
| image refused | `no_vision` | "The model `{model}` can't read images. Pick a vision model for Explain screen." |
| missing `choices` / bad JSON | `bad_response` | "The model sent back something Kami couldn't read." |

**Check before building:** OpenRouter's exact status codes and error bodies
(especially 402 and the "model doesn't support images" case) are assumptions. Read
<https://openrouter.ai/docs/api-reference/errors> and make one real request with a
text-only model plus an image to record the actual body. Base `no_vision`
detection on that, and fall back to the generic 4xx message if unsure.

If the error body has `{"error": {"message": ...}}`, append it to the message,
shortened to about 200 characters. Never include the request headers, because
they contain the key.

## Files

| File | Change |
|---|---|
| `src/kami/llm/client.py` | `LLMError`, `_classify(response)`, wrap `httpx` exceptions, inject an `httpx.Client` |
| `src/kami/llm/__init__.py` | export `LLMError` |
| `tests/test_llm_client.py` | new |

## Implementation

1. Make the HTTP layer testable: let `LLMClient.__init__` accept an optional
   `http: httpx.Client | None` (default: a new `httpx.Client(timeout=...)`) and use
   `self.http.post(...)`. Tests pass `httpx.Client(transport=httpx.MockTransport(handler))`.
   Nothing touches the real network.
2. In `chat()`:
   - Catch `httpx.TimeoutException` and raise `LLMError("timeout", ...)`.
   - Catch `httpx.ConnectError` and raise `LLMError("network", ...)`.
   - Turn non-2xx responses into the right `kind` with `_classify`.
   - Parse the body defensively. Raise `bad_response` if `choices[0].message.content`
     is missing or not a string.
3. Use `raise ... from exc` so the original error is kept for logging (Task 5).
4. Leave the `ui/` code alone. `worker.py` already shows `str(exc)` through `_error`.

## Tests — `tests/test_llm_client.py`

Use a helper `client_with(handler)` that builds an `LLMClient` with a
`MockTransport` and a fake key.

- [ ] `test_returns_content_on_success`: 200 with a normal body returns the text
- [ ] `test_sends_bearer_key_and_model`: the handler checks the `Authorization` header and `model` in the JSON body
- [ ] `test_image_request_has_data_url`: `ask_about_image` sends `image_url` starting with `data:image/png;base64,`
- [ ] `test_missing_key_raises_before_network`: the handler must never be called
- [ ] `test_status_codes_map_to_kinds`: parametrized over 401, 402, 429, 500, 503 → expected `kind`
- [ ] `test_timeout_maps_to_timeout`: the handler raises `httpx.ReadTimeout`
- [ ] `test_connect_error_maps_to_network`: the handler raises `httpx.ConnectError`
- [ ] `test_bad_body_maps_to_bad_response`: 200 with `{}` and 200 with non-JSON text
- [ ] `test_provider_message_is_included_and_truncated`: a long `error.message` is cut to ≤ 200 chars
- [ ] `test_error_never_contains_api_key`: for every error kind, `"sk-test"` is not in `str(err)`

## Manual check

- [ ] Wrong key in env → panel shows the "rejected" sentence
- [ ] Wi-Fi off → panel shows the "can't reach" sentence
- [ ] Text-only model + Explain screen → panel shows the "can't read images" sentence

## Done when

- [ ] All tests above pass in CI
- [ ] No raw `httpx` text or Python traceback can reach the panel from `LLMClient`
- [ ] `/security-check` run on the diff (the key must not leak into messages)

## Commits

1. `inject http client into llm client`
2. `map llm failures to plain-language errors`
