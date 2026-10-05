"""Minimal client for OpenRouter or any OpenAI-compatible chat endpoint."""
from __future__ import annotations

import base64

import httpx

from kami.config import LLMConfig


class MissingAPIKey(RuntimeError):
    pass


class LLMClient:
    def __init__(self, cfg: LLMConfig, timeout: float = 90.0,
                 http: httpx.Client | None = None) -> None:
        self.cfg = cfg
        self.timeout = timeout
        # Tests pass an httpx.Client with a MockTransport, so nothing touches the network.
        self.http = http or httpx.Client(timeout=timeout)

    def chat(self, messages: list[dict]) -> str:
        if not self.cfg.api_key:
            raise MissingAPIKey(
                "No API key. Set KAMI_API_KEY or OPENROUTER_API_KEY, "
                "or api_key in ~/.config/kami/config.toml."
            )
        response = self.http.post(
            f"{self.cfg.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.cfg.api_key}",
                "X-Title": "Kami",
            },
            json={"model": self.cfg.model, "messages": messages},
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

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
