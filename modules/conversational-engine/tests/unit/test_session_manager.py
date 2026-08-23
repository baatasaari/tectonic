from __future__ import annotations

import pytest

from conversational_engine.config import ConversationalEngineSettings, HandoffConfig
from conversational_engine.core.domain import (
    Channel,
    HandoffTriggerReason,
    PersonaConfigRecord,
    SessionStatus,
)

pytestmark = pytest.mark.asyncio


async def test_happy_path_turn_completes_and_persists(harness):
    session = await harness.manager.create_session(
        tenant_id="tenant-a", channel=Channel.WEB, persona_config_ref="default", trace_id="trace-1"
    )

    result = await harness.manager.handle_turn(session, "What are your hours?")

    assert result.refused is False
    assert result.outbound_message.content == "Sure, here's an answer."
    assert result.handoff_event is None
    messages = await harness.repository.list_messages(session.id)
    assert [m.direction.value for m in messages] == ["inbound", "outbound"]


async def test_denied_topic_short_circuits_before_llm_call(harness):
    harness.repository.seed_persona(
        PersonaConfigRecord(id="restricted", tenant_id="tenant-a", name="restricted", denied_topics=["medical advice"])
    )
    session = await harness.manager.create_session(
        tenant_id="tenant-a", channel=Channel.WEB, persona_config_ref="restricted", trace_id="trace-1"
    )

    result = await harness.manager.handle_turn(session, "Can you give me medical advice?")

    assert result.refused is True
    assert result.refusal_category == "denied_topic"
    assert harness.llm_gateway.calls == []  # never reached the LLM Gateway


async def test_guardrails_blocked_output_produces_refusal(harness):
    harness.guardrails.block_next = True
    harness.guardrails.violation_category = "policy_violation"
    session = await harness.manager.create_session(
        tenant_id="tenant-a", channel=Channel.WEB, persona_config_ref="default", trace_id="trace-1"
    )

    result = await harness.manager.handle_turn(session, "Tell me something.")

    assert result.refused is True
    assert result.refusal_category == "policy_violation"


async def test_explicit_handoff_phrase_triggers_handoff(harness):
    session = await harness.manager.create_session(
        tenant_id="tenant-a", channel=Channel.WEB, persona_config_ref="default", trace_id="trace-1"
    )

    result = await harness.manager.handle_turn(session, "I want to speak to a human please.")

    assert result.handoff_event is not None
    assert result.handoff_event.trigger_reason == HandoffTriggerReason.EXPLICIT
    assert len(harness.human_oversight.requests) == 1
    updated = await harness.repository.get_session(session.id)
    assert updated.status == SessionStatus.HANDED_OFF


async def test_high_emotion_triggers_handoff(harness_factory):
    settings = ConversationalEngineSettings(handoff=HandoffConfig(emotion_score_threshold=0.5))
    harness = harness_factory(settings=settings)
    session = await harness.manager.create_session(
        tenant_id="tenant-a", channel=Channel.WEB, persona_config_ref="default", trace_id="trace-1"
    )

    result = await harness.manager.handle_turn(
        session, "This is UNACCEPTABLE!! I am furious, worst service, refund now!!!"
    )

    assert result.handoff_event is not None
    assert result.handoff_event.trigger_reason == HandoffTriggerReason.EMOTION


async def test_repeated_refusals_trigger_handoff(harness_factory):
    settings = ConversationalEngineSettings(handoff=HandoffConfig(repeated_refusal_threshold=2, emotion_score_threshold=0.99))
    harness = harness_factory(settings=settings)
    harness.guardrails.block_next = True
    session = await harness.manager.create_session(
        tenant_id="tenant-a", channel=Channel.WEB, persona_config_ref="default", trace_id="trace-1"
    )

    first = await harness.manager.handle_turn(session, "First question.")
    assert first.refused is True
    assert first.handoff_event is None  # only one refusal so far

    session = await harness.repository.get_session(session.id)
    second = await harness.manager.handle_turn(session, "Second question.")

    assert second.refused is True
    assert second.handoff_event is not None
    assert second.handoff_event.trigger_reason == HandoffTriggerReason.REPEATED_REFUSAL


async def test_no_more_turns_after_handoff_is_not_reprocessed_by_engine(harness):
    # Once handed off, the session manager still processes a turn if asked
    # (the API layer is what blocks further messages on a non-active
    # session — see routes_sessions.send_message) but must not fire a
    # second handoff event for an already-handed-off session.
    session = await harness.manager.create_session(
        tenant_id="tenant-a", channel=Channel.WEB, persona_config_ref="default", trace_id="trace-1"
    )
    first = await harness.manager.handle_turn(session, "speak to a human")
    assert first.handoff_event is not None

    handed_off_session = await harness.repository.get_session(session.id)
    second = await harness.manager.handle_turn(handed_off_session, "speak to a human again")

    assert second.handoff_event is None
    assert len(harness.human_oversight.requests) == 1


async def test_manual_handoff(harness):
    session = await harness.manager.create_session(
        tenant_id="tenant-a", channel=Channel.WEB, persona_config_ref="default", trace_id="trace-1"
    )
    event = await harness.manager.manual_handoff(session, "customer asked for a manager")

    assert event.trigger_reason == HandoffTriggerReason.EXPLICIT
    updated = await harness.repository.get_session(session.id)
    assert updated.status == SessionStatus.HANDED_OFF
    assert harness.auditability.events[-1]["detail"] == "customer asked for a manager"
