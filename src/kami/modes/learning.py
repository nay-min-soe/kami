"""Learning mode: explain a circled screen region and annotate it like a whiteboard.

The model returns JSON with an explanation plus annotations whose coordinates
are normalized (0-1) to the captured region, so the overlay can draw circles,
arrows and short notes right on top of the screen.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

SYSTEM_PROMPT = """You are Kami, a patient teacher explaining what is on the user's screen.
Reply with ONLY a JSON object, no code fences:
{
  "explanation": "a short, clear explanation (max ~120 words)",
  "annotations": [
    {"type": "circle", "x": 0.5, "y": 0.4, "r": 0.12, "label": "key point"},
    {"type": "arrow", "from": [0.1, 0.9], "to": [0.45, 0.5], "label": "look here"},
    {"type": "text", "x": 0.05, "y": 0.05, "text": "short note"}
  ]
}
Coordinates are fractions of the image width/height (0 to 1). Use at most 4
annotations and keep every label under 6 words."""

USER_PROMPT = "Explain this part of my screen and mark the most important parts."


@dataclass
class Annotation:
    type: str                 # "circle" | "arrow" | "text"
    x: float = 0.0
    y: float = 0.0
    r: float = 0.0
    x2: float = 0.0           # arrow head
    y2: float = 0.0
    label: str = ""


@dataclass
class Lesson:
    explanation: str
    annotations: list[Annotation] = field(default_factory=list)


def _clamp(value, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return lo


def parse_lesson(raw: str) -> Lesson:
    """Parse the model reply. Falls back to plain text if the JSON is broken."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    match = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        data = json.loads(match.group(0) if match else text)
    except (json.JSONDecodeError, AttributeError):
        return Lesson(explanation=raw.strip())
    if not isinstance(data, dict):
        return Lesson(explanation=raw.strip())

    annotations: list[Annotation] = []
    for item in data.get("annotations", [])[:4]:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        label = str(item.get("label") or item.get("text") or "")[:60]
        if kind == "circle":
            annotations.append(Annotation("circle", _clamp(item.get("x")), _clamp(item.get("y")),
                                          r=_clamp(item.get("r", 0.1), 0.02, 0.5), label=label))
        elif kind == "arrow":
            start = item.get("from") or [0, 0]
            end = item.get("to") or [0, 0]
            if len(start) == 2 and len(end) == 2:
                annotations.append(Annotation("arrow", _clamp(start[0]), _clamp(start[1]),
                                              x2=_clamp(end[0]), y2=_clamp(end[1]), label=label))
        elif kind == "text" and label:
            annotations.append(Annotation("text", _clamp(item.get("x")), _clamp(item.get("y")),
                                          label=label))
    return Lesson(explanation=str(data.get("explanation", "")).strip(), annotations=annotations)


def explain_region(client, png: bytes) -> Lesson:
    return parse_lesson(client.ask_about_image(png, USER_PROMPT, system=SYSTEM_PROMPT))
