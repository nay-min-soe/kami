"""Minimal client for OpenRouter or any OpenAI-compatible chat endpoint.

Every failure is raised as LLMError: a `kind` for code (and logs) plus one plain
sentence for the panel. The worker shows str(exc), so no raw httpx text reaches the UI.
"""
from __future__ import annotations

import base64
import json
import logging
import threading
import time
from collections.abc import Callable
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
        body = self._request("POST", "/chat/completions", self.timeout, json={
            "model": self.cfg.model, "messages": messages})
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            content = None
        if not isinstance(content, str):
            raise LLMError("bad_response", "The model sent back something Kami couldn't read. "
                                           "Try again, or pick another model.")
        return content

    def chat_stream(self, messages: list[dict], on_delta: Callable[[str], None],
                    cancel: threading.Event | None = None) -> str:
        """Stream a reply, calling on_delta for each piece. Returns the full text."""
        start = time.monotonic()
        first: list[float] = []

        def delta(piece: str) -> None:
            if not first:
                first.append(time.monotonic() - start)
            on_delta(piece)

        try:
            text = self._chat_stream(messages, delta, cancel)
        except LLMError as exc:
            # Timings and the kind only: never the prompt, the reply or the key.
            log.warning("stream ended kind=%s model=%s first_token=%s took=%.1fs", exc.kind,
                        self.cfg.model, f"{first[0]:.1f}s" if first else "none",
                        time.monotonic() - start)
            raise
        log.info("stream ok model=%s first_token=%.1fs took=%.1fs",
                 self.cfg.model, first[0], time.monotonic() - start)
        return text

    def _chat_stream(self, messages: list[dict], on_delta: Callable[[str], None],
                     cancel: threading.Event | None) -> str:
        if not self.cfg.api_key:
            raise MissingAPIKey()
        pieces: list[str] = []
        try:
            with self.http.stream("POST", f"{self.cfg.base_url}/chat/completions",
                                  headers=self._headers(), timeout=self.timeout,
                                  json={"model": self.cfg.model, "messages": messages,
                                        "stream": True}) as response:
                if not response.is_success:
                    response.read()
                    raise self._error(response.status_code, _json_error(response))
                # httpx's read timeout applies between lines, so a long, steady answer is fine.
                for line in response.iter_lines():
                    if cancel is not None and cancel.is_set():
                        raise LLMError("cancelled", "Stopped.")
                    if not line.startswith("data:"):
                        continue   # blank lines and ": OPENROUTER PROCESSING" keep-alives
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except ValueError:
                        continue
                    if not isinstance(chunk, dict):
                        continue
                    if chunk.get("error"):
                        # Mid-stream failures arrive with status 200.
                        raise self._error(200, chunk["error"])
                    piece = _delta_text(chunk)
                    if piece:
                        pieces.append(piece)
                        on_delta(piece)
        except httpx.TimeoutException as exc:
            raise LLMError("timeout", f"The model went quiet for {self.timeout:.0f} s. "
                                      "Try again.") from exc
        except httpx.TransportError as exc:
            raise LLMError("network", f"Lost the connection to {self._host()}. Check your "
                                      "internet connection and try again.") from exc
        if not pieces:
            raise LLMError("bad_response", "The model sent back something Kami couldn't read. "
                                           "Try again, or pick another model.")
        return "".join(pieces)

    def list_models(self, timeout: float = 5.0) -> list[dict]:
        """The endpoint's model list (GET /models). Free: it sends no prompt and uses no tokens."""
        body = self._request("GET", "/models", timeout)
        models = body.get("data")
        if not isinstance(models, list):
            raise LLMError("bad_response", "The endpoint's model list couldn't be read.")
        return [m for m in models if isinstance(m, dict)]

    def _request(self, method: str, path: str, timeout: float, **kwargs) -> dict:
        """Send one request and return the JSON body, or raise a plain-language LLMError."""
        try:
            response = self.http.request(method, f"{self.cfg.base_url}{path}",
                                         headers=self._headers(), timeout=timeout, **kwargs)
        except httpx.TimeoutException as exc:
            raise LLMError("timeout", f"The model took longer than {timeout:.0f} s "
                                      "to answer. Try again.") from exc
        except httpx.TransportError as exc:
            raise LLMError("network", f"Can't reach {self._host()}. Check your internet connection "
                                      "or base_url in config.toml.") from exc

        try:
            body = response.json()
        except ValueError:
            body = None
        error = body.get("error") if isinstance(body, dict) else None
        if not response.is_success or error:
            # OpenRouter can also report a failure inside a 200 reply, with no choices.
            raise self._error(response.status_code, error)
        return body if isinstance(body, dict) else {}

    def _headers(self) -> dict:
        headers = {"X-Title": "Kami"}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"
        return headers

    def _host(self) -> str:
        return urlsplit(self.cfg.base_url).hostname or self.cfg.base_url

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
            if self.cfg.api_key:
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
        messages = [{"role": "system", "content": system}] if system else []
        messages.append({"role": "user", "content": [{"type": "text", "text": prompt},
                                                     image_part(png)]})
        return self.chat(messages)


def _json_error(response: httpx.Response):
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("error") if isinstance(body, dict) else None


def _delta_text(chunk: dict) -> str:
    try:
        piece = chunk["choices"][0]["delta"].get("content")
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""
    return piece if isinstance(piece, str) else ""


def image_part(png: bytes) -> dict:
    """One PNG as an OpenAI-style message part (base64 data URL)."""
    data_url = "data:image/png;base64," + base64.b64encode(png).decode()
    return {"type": "image_url", "image_url": {"url": data_url}}
