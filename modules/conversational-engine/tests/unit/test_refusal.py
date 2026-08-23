from conversational_engine.core.refusal import RefusalComposer


def test_known_category_uses_its_template():
    text = RefusalComposer().compose("denied_topic", "medical advice")
    assert "medical advice" in text
    assert "topic" in text.lower()


def test_unknown_category_falls_back_to_default_template():
    text = RefusalComposer().compose("something_new", "custom detail")
    assert "custom detail" in text


def test_missing_detail_falls_back_to_category_name():
    text = RefusalComposer().compose("pii_risk")
    assert "pii_risk" in text
