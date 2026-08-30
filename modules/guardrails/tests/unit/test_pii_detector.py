from guardrails.core.pii_detector import detect, detect_and_redact


def test_detects_email():
    found = detect("contact me at alice@example.com please", ["EMAIL"])
    assert "EMAIL" in found


def test_detects_phone_number():
    found = detect("call me at 555-123-4567", ["PHONE_NUMBER"])
    assert "PHONE_NUMBER" in found


def test_no_detection_for_clean_text():
    found = detect("the weather is nice today", ["EMAIL", "PHONE_NUMBER", "CREDIT_CARD"])
    assert found == {}


def test_redacts_email_and_returns_entity_list():
    redacted, entities = detect_and_redact("email me at bob@example.com", ["EMAIL"])
    assert "bob@example.com" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert entities == ["EMAIL"]


def test_redact_only_configured_entity_types():
    redacted, entities = detect_and_redact("email me at bob@example.com", ["PHONE_NUMBER"])
    assert redacted == "email me at bob@example.com"
    assert entities == []


def test_person_heuristic_detects_capitalized_name():
    found = detect("Please contact John Smith about this.", ["PERSON"])
    assert "PERSON" in found
