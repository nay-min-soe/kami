from kami.modes.learning import parse_lesson


def test_parses_annotations_and_clamps():
    raw = '''```json
    {"explanation": "Gradient descent finds the minimum.",
     "annotations": [
       {"type": "circle", "x": 0.5, "y": 1.7, "r": 0.2, "label": "minimum"},
       {"type": "arrow", "from": [0, 1], "to": [0.5, 0.5], "label": "step"},
       {"type": "text", "x": 0.1, "y": 0.1, "text": "learning rate"}
     ]}
    ```'''
    lesson = parse_lesson(raw)
    assert lesson.explanation.startswith("Gradient")
    assert [a.type for a in lesson.annotations] == ["circle", "arrow", "text"]
    assert lesson.annotations[0].y == 1.0          # clamped into the region
    assert lesson.annotations[2].label == "learning rate"


def test_falls_back_to_plain_text():
    lesson = parse_lesson("Sorry, here is just a plain answer.")
    assert lesson.explanation == "Sorry, here is just a plain answer."
    assert lesson.annotations == []


def test_caps_annotation_count():
    items = ",".join('{"type":"text","x":0,"y":0,"text":"n"}' for _ in range(10))
    lesson = parse_lesson('{"explanation":"x","annotations":[%s]}' % items)
    assert len(lesson.annotations) == 4
