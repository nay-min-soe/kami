from kami.conversation import Conversation


def test_first_question_has_system_and_user():
    messages = Conversation(system="be brief").messages_with("hi")
    assert messages == [{"role": "system", "content": "be brief"},
                        {"role": "user", "content": "hi"}]


def test_record_adds_pair():
    chat = Conversation()
    chat.record("q1", "a1")
    assert chat.messages_with("q2") == [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
    ]


def test_messages_with_does_not_mutate():
    chat = Conversation(system="s")
    chat.messages_with("hi")
    chat.messages_with("hi")
    assert chat.turns == []


def test_no_system_when_none():
    messages = Conversation(system=None).messages_with("hi")
    assert [m["role"] for m in messages] == ["user"]


def test_trims_oldest_pairs_by_turns():
    chat = Conversation(max_turns=4)
    for i in range(5):
        chat.record(f"q{i}", f"a{i}")
    assert [t.text for t in chat.turns] == ["q3", "a3", "q4", "a4"]
    roles = [m["role"] for m in chat.messages_with("next")]
    assert roles == ["user", "assistant", "user", "assistant", "user"]


def test_trims_by_chars_keeps_new_question():
    chat = Conversation(max_chars=100)
    chat.record("old", "x" * 90)
    chat.record("q", "short")
    messages = chat.messages_with("new question " * 3)
    assert all("x" * 90 != m["content"] for m in messages)
    assert messages[-1] == {"role": "user", "content": "new question " * 3}
    assert [m["content"] for m in messages[:2]] == ["q", "short"]


def test_huge_question_still_sent_alone():
    chat = Conversation(max_chars=10)
    chat.record("q", "a")
    assert chat.messages_with("y" * 50) == [{"role": "user", "content": "y" * 50}]


def test_clear_empties_history():
    chat = Conversation()
    chat.record("q", "a")
    chat.clear()
    assert chat.turns == []
    assert chat.chars == 0


def test_works_with_fake_llm(fake_llm):
    chat = Conversation(system="s")
    first = chat.messages_with("what's a list?")
    chat.record("what's a list?", fake_llm.chat(first))
    second = chat.messages_with("and a tuple?")
    fake_llm.chat(second)
    sent = fake_llm.calls[-1]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[2]["content"] == "fake reply"


def test_follow_up_sends_image_part():
    from kami.modes.learning import Lesson, follow_up_conversation

    chat = follow_up_conversation(b"\x89PNG", Lesson("A bar chart."))
    messages = chat.messages_with("why?")
    parts = messages[1]["content"]
    assert messages[1]["role"] == "user"
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert messages[2] == {"role": "assistant", "content": "A bar chart."}
    assert messages[-1] == {"role": "user", "content": "why?"}


def test_image_turn_survives_trimming():
    chat = Conversation(max_turns=4, pinned=2)   # the pinned pair counts toward max_turns
    chat.record("look", "a chart", image=b"png")
    for i in range(5):
        chat.record(f"q{i}", f"a{i}")
    turns = chat.turns
    assert turns[0].image == b"png"
    assert [t.text for t in turns] == ["look", "a chart", "q4", "a4"]
    assert chat.messages_with("next")[0]["content"][1]["type"] == "image_url"


def test_image_turn_survives_char_trimming():
    chat = Conversation(max_chars=50, pinned=2)
    chat.record("look", "a chart", image=b"png")
    chat.record("q", "x" * 100)
    assert [t.text for t in chat.turns] == ["look", "a chart"]


def test_clear_drops_image():
    chat = Conversation()
    chat.record("look", "a chart", image=b"png")
    assert chat.has_image
    chat.clear()
    assert not chat.has_image
    assert all(t.image is None for t in chat.turns)
