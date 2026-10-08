"""Short, in-memory chat history for Ask and Explain-screen follow-ups.

No Qt, and nothing (text or screenshot) is ever written to disk.
"""
from __future__ import annotations

from dataclasses import dataclass

from kami.llm import image_part


@dataclass
class Turn:
    role: str                    # "user" | "assistant"
    text: str
    image: bytes | None = None


class Conversation:
    def __init__(self, system: str | None = None,
                 max_turns: int = 20, max_chars: int = 24_000, pinned: int = 0) -> None:
        self.system = system
        self.max_turns = max_turns
        self.max_chars = max_chars
        self.pinned = pinned   # leading turns trimming never drops (the capture + its explanation)
        self._turns: list[Turn] = []

    @property
    def turns(self) -> list[Turn]:
        return list(self._turns)

    @property
    def has_image(self) -> bool:
        return any(t.image for t in self._turns)

    @property
    def chars(self) -> int:
        return sum(len(t.text) for t in self._turns)

    def messages_with(self, question: str) -> list[dict]:
        """History plus the pending question, trimmed. Doesn't change the history."""
        messages = [{"role": "system", "content": self.system}] if self.system else []
        messages += [self._message(t) for t in self._trimmed(self._turns, len(question))]
        messages.append({"role": "user", "content": question})
        return messages

    def record(self, question: str, answer: str, image: bytes | None = None) -> None:
        """Add a finished question/answer pair. Call only when the reply arrived."""
        self._turns = self._trimmed(self._turns + [Turn("user", question, image),
                                                   Turn("assistant", answer)], 0)

    def clear(self) -> None:
        self._turns = []

    def _trimmed(self, turns: list[Turn], extra_chars: int) -> list[Turn]:
        # Turns always come in user/assistant pairs, so dropping two never splits one.
        turns = list(turns)
        while len(turns) > self.pinned and (
                len(turns) > self.max_turns
                or sum(len(t.text) for t in turns) + extra_chars > self.max_chars):
            del turns[self.pinned:self.pinned + 2]
        return turns

    @staticmethod
    def _message(turn: Turn) -> dict:
        if turn.image:
            return {"role": turn.role,
                    "content": [{"type": "text", "text": turn.text}, image_part(turn.image)]}
        return {"role": turn.role, "content": turn.text}
