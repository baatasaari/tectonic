from conversational_engine.core.domain import PersonaConfigRecord
from conversational_engine.core.persona import PersonaEngine


def _persona(**overrides) -> PersonaConfigRecord:
    defaults = {"id": "p1", "tenant_id": "tenant-a", "name": "friendly", "tone_settings": {"tone": "warm"}}
    defaults.update(overrides)
    return PersonaConfigRecord(**defaults)


def test_denied_topic_short_circuits_prompt_build():
    persona = _persona(denied_topics=["medical advice"])
    result = PersonaEngine().build_prompt(persona, [], "Can you give me medical advice about this rash?")
    assert result.denied_topic == "medical advice"
    assert result.prompt_context is None


def test_allowed_message_builds_prompt_context():
    persona = _persona(denied_topics=["medical advice"], allowed_topics=["billing"])
    result = PersonaEngine().build_prompt(persona, [], "What's my current balance?")
    assert result.denied_topic is None
    assert result.prompt_context["message"] == "What's my current balance?"
    assert result.prompt_context["persona_name"] == "friendly"
    assert result.prompt_context["allowed_topics"] == ["billing"]


def test_history_is_truncated_to_last_20():
    from conversational_engine.core.domain import MessageDirection, MessageRecord, new_id

    history = [
        MessageRecord(id=new_id(), session_id="s1", direction=MessageDirection.INBOUND, content=f"msg {i}")
        for i in range(30)
    ]
    result = PersonaEngine().build_prompt(_persona(), history, "latest")
    assert len(result.prompt_context["history"]) == 20
    assert result.prompt_context["history"][-1]["content"] == "msg 29"
