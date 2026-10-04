"""Meetings mode: transcripts, notes and quick research.

Status: summarizing works; live capture is a TODO.

Plan:
  1. Capture system audio + mic (PipeWire/PulseAudio monitor source,
     e.g. via the `sounddevice` package).
  2. Transcribe in chunks (local Whisper / faster-whisper, or an API).
  3. Feed the rolling transcript to `summarize_transcript` for notes.
"""
from __future__ import annotations

NOTES_PROMPT = """Turn this meeting transcript into notes:
- 3-6 bullet summary
- decisions made
- action items (owner if mentioned)
- open questions worth a quick search

Transcript:
{transcript}"""


def summarize_transcript(client, transcript: str) -> str:
    return client.ask(NOTES_PROMPT.format(transcript=transcript))


def start_capture():
    raise NotImplementedError("Audio capture is not built yet. See the plan above.")
