"""Unit tests for the Workflow Engine routing path (ticket #82's
WorkflowEngineClient port, session_manager.py's
_handle_turn_via_workflow_engine) -- gated behind
settings.workflow_routing.enabled, default off."""
from __future__ import annotations

import pytest

from conversational_engine.config import ConversationalEngineSettings, WorkflowRoutingConfig
from conversational_engine.core.domain import Channel, HandoffTriggerReason, SessionStatus

pytestmark = pytest.mark.asyncio


def _routing_enabled_settings() -> ConversationalEngineSettings:
    return ConversationalEngineSettings(workflow_routing=WorkflowRoutingConfig(enabled=True))


async def test_routing_disabled_by_default_keeps_calling_llm_gateway_directly(harness):
    """Default settings (workflow_routing.enabled=False): the workflow_engine
    client, even though wired, must never be called."""
    session = await harness.manager.create_session(
        tenant_id="tenant-a", channel=Channel.WEB, persona_config_ref="default", trace_id="trace-1"
    )

    result = await harness.manager.handle_turn(session, "What are your hours?")

    assert result.outbound_message.content == "Sure, here's an answer."
    assert harness.workflow_engine.calls == []


async def test_completed_instance_becomes_the_outbound_message(harness_factory):
    harness = harness_factory(settings=_routing_enabled_settings())
    harness.workflow_engine.queue_response(
        {
            "id": "wf-instance-1", "status": "completed", "trace_id": "trace-1",
            "context": {"respond": {"content": "Your order #A1029 shipped, arriving 2026-09-02."}},
        }
    )
    session = await harness.manager.create_session(
        tenant_id="acme", channel=Channel.WEB, persona_config_ref="default", trace_id="trace-1"
    )

    result = await harness.manager.handle_turn(session, "Where's my order #A1029?")

    assert result.refused is False
    assert result.handoff_event is None
    assert result.outbound_message.content == "Your order #A1029 shipped, arriving 2026-09-02."
    assert harness.workflow_engine.calls == [
        {
            "definition_id": "support-agent-v1",
            "initial_context": {"message": "Where's my order #A1029?"},
            "tenant_id": "acme",
        }
    ]


async def test_paused_for_approval_records_a_workflow_escalation_handoff(harness_factory):
    harness = harness_factory(settings=_routing_enabled_settings())
    harness.workflow_engine.queue_response(
        {"id": "wf-instance-2", "status": "paused_for_approval", "trace_id": "trace-2", "context": {}}
    )
    session = await harness.manager.create_session(
        tenant_id="acme", channel=Channel.WEB, persona_config_ref="default", trace_id="trace-2"
    )

    result = await harness.manager.handle_turn(session, "I want a refund for order #A1029, it's $850.")

    assert result.refused is False
    assert result.handoff_event is not None
    assert result.handoff_event.trigger_reason == HandoffTriggerReason.WORKFLOW_ESCALATION
    assert result.handoff_event.target == "workflow-instance:wf-instance-2"
    stored = await harness.repository.get_session(session.id)
    assert stored.status == SessionStatus.HANDED_OFF
    assert len(harness.auditability.events) == 1
    assert harness.auditability.events[0]["event_type"] == "conversation.handoff"


async def test_failed_instance_produces_a_refusal(harness_factory):
    harness = harness_factory(settings=_routing_enabled_settings())
    harness.workflow_engine.queue_response({"id": "wf-instance-3", "status": "failed", "trace_id": "trace-3", "context": {}})
    session = await harness.manager.create_session(
        tenant_id="acme", channel=Channel.WEB, persona_config_ref="default", trace_id="trace-3"
    )

    result = await harness.manager.handle_turn(session, "hello")

    assert result.refused is True
    assert result.handoff_event is None
