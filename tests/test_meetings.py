import pytest

from kami.modes import meetings


def test_summarize_puts_transcript_in_prompt(fake_llm):
    meetings.summarize_transcript(fake_llm, "Ana: ship it Friday.")
    prompt = fake_llm.calls[0]["prompt"]
    assert "Ana: ship it Friday." in prompt
    assert "action items" in prompt


def test_summarize_returns_model_text(fake_llm):
    fake_llm.reply = "- shipped"
    assert meetings.summarize_transcript(fake_llm, "hello") == "- shipped"


def test_transcript_with_braces_is_safe(fake_llm):
    meetings.summarize_transcript(fake_llm, "use {x} and {transcript} as-is")
    assert "use {x} and {transcript} as-is" in fake_llm.calls[0]["prompt"]


def test_start_capture_not_implemented():
    # Remove in Phase 4, when live capture is built.
    with pytest.raises(NotImplementedError):
        meetings.start_capture()
