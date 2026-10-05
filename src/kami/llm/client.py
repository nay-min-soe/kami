"""Minimal client for OpenRouter or any OpenAI-compatible chat endpoint.

Every failure is raised as LLMError: a `kind` for code (and logs) plus one plain
sentence for the panel. The worker shows str(exc), so no raw httpx text reaches the UI.
"""
from __future__ import annotations

import base64
import logging
import time
from urllib.parse import urlsplit

import httpx

from kami.config import LLMConfig

log = logging.getLogger(__name__)

PROVIDER_DETAIL_MAX = 200  # characters of the provider's own error message we pass on


class LLMError(RuntimeError):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


class MissingAPIKey(LLMError):
    def __init__(self) -> None:
        super().__init__("missing_key", "No API key. Set KAMI_API_KEY or OPENROUTER_API_KEY, "
                                        "or api_key in ~/.config/kami/config.toml.")


class LLMClient:
    def __init__(self, cfg: LLMConfig, timeout: float = 90.0,
                 http: httpx.Client | None = None) -> None:
        self.cfg = cfg
        self.timeout = timeout
        # Tests pass an httpx.Client with a MockTransport, so nothing touches the network.
        self.http = http or httpx.Client(timeout=timeout)

    def chat(self, messages: list[dict]) -> str:
        start = time.monotonic()
        try:
            content = self._chat(messages)
        except LLMError as exc:
            # Only the kind and model: never the prompt, the reply or the key.
            log.warning("chat failed kind=%s model=%s took=%.1fs",
                        exc.kind, self.cfg.model, time.monotonic() - start)
            raise
        log.info("chat ok model=%s took=%.1fs", self.cfg.model, time.monotonic() - start)
        return content

    def _chat(self, messages: list[dict]) -> str:
        if not self.cfg.api_key:
            raise MissingAPIKey()
        host = urlsplit(self.cfg.base_url).hostname or self.cfg.base_url
        try:
            response = self.http.post(
                f"{self.cfg.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.cfg.api_key}",
                    "X-Title": "Kami",
                },
                json={"model": self.cfg.model, "messages": messages},
            )
        except httpx.TimeoutException as exc:
            raise LLMError("timeout", f"The model took longer than {self.timeout:.0f} s "
                                      "to answer. Try again.") from exc
        except httpx.TransportError as exc:
            raise LLMError("network", f"Can't reach {host}. Check your internet connection "
                                      "or base_url in config.toml.") from exc

        try:
            body = response.json()
        except ValueError:
            body = None
        error = body.get("error") if isinstance(body, dict) else None
        if not response.is_success or error:
            # OpenRouter can also report a failure inside a 200 reply, with no choices.
            raise self._error(response.status_code, error)
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            content = None
        if not isinstance(content, str):
            raise LLMError("bad_response", "The model sent back something Kami couldn't read. "
                                           "Try again, or pick another model.")
        return content

    def _error(self, status: int, error) -> LLMError:
        detail = ""
        if isinstance(error, dict):
            detail = str(error.get("message") or "")
        if status < 400:  # an error inside a 200 reply: the provider failed mid-answer
            code = error.get("code") if isinstance(error, dict) else None
            status = code if isinstance(code, int) else 502
        if status in (401, 403):
            kind, message = "auth", ("Your API key was rejected. "
                                     "Check KAMI_API_KEY or OPENROUTER_API_KEY.")
        elif status == 402:
            kind, message = "credits", "Your account is out of credit. Top up, then try again."
        elif status == 429:
            kind, message = "rate_limit", "Too many requests. Wait a minute and try again."
        elif status == 404 and "image input" in detail.lower():
            kind, message = "no_vision", (f"The model '{self.cfg.model}' can't read images. "
                                          "Pick a vision model for Explain screen.")
        elif status >= 500:
            kind, message = "server", "The model provider had an error. Try again shortly."
        else:
            kind, message = "request", f"The model provider refused the request (error {status})."
        if detail:
            detail = detail.replace(self.cfg.api_key, "[redacted]")  # never echo the key
            if len(detail) > PROVIDER_DETAIL_MAX:
                detail = detail[:PROVIDER_DETAIL_MAX - 1] + "…"
            message += f" Provider says: {detail}"
        return LLMError(kind, message)

    def ask(self, prompt: str, system: str | None = None) -> str:
        messages = [{"role": "system", "content": system}] if system else []
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages)

    def ask_about_image(self, png: bytes, prompt: str, system: str | None = None) -> str:
        data_url = "data:image/png;base64," + base64.b64encode(png).decode()
        messages = [{"role": "system", "content": system}] if system else []
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        })
        return self.chat(messages)
