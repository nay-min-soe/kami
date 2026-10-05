import pytest


class FakeLLM:
    """Stands in for LLMClient: records every call and returns a preset reply."""

    def __init__(self, reply: str = "fake reply") -> None:
        self.reply = reply
        self.calls: list[dict] = []

    def ask(self, prompt: str, system: str | None = None) -> str:
        self.calls.append({"prompt": prompt, "system": system})
        return self.reply

    def ask_about_image(self, png: bytes, prompt: str, system: str | None = None) -> str:
        self.calls.append({"png": png, "prompt": prompt, "system": system})
        return self.reply


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()
