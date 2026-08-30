import pytest

from human_oversight.core.domain import (
    RequestNotDecidableError,
    RequestNotFoundError,
    RequestStatus,
)


async def test_approve_decision_marks_request_decided(harness):
    request = await harness.queue_manager.enqueue(
        tenant_id="t1", requesting_module="workflow_engine", requesting_ref="wf-1:approval-1", context={},
    )
    decision = await harness.decision_capture.capture(
        "t1", request.id, decision="approved", decided_by="reviewer-a", decision_reason="looks fine",
    )
    assert decision.decision.value == "approved"

    updated = await harness.repository.get_request("t1", request.id)
    assert updated.status == RequestStatus.DECIDED


async def test_decision_triggers_callback_with_correct_module_and_ref(harness):
    request = await harness.queue_manager.enqueue(
        tenant_id="t1", requesting_module="workflow_engine", requesting_ref="wf-1:approval-1", context={},
    )
    await harness.decision_capture.capture("t1", request.id, decision="approved", decided_by="reviewer-a")

    assert len(harness.callback_dispatcher.calls) == 1
    call = harness.callback_dispatcher.calls[0]
    assert call["requesting_module"] == "workflow_engine"
    assert call["requesting_ref"] == "wf-1:approval-1"
    assert call["decision"] == "approved"


async def test_override_creates_override_record_and_audit_event(harness):
    request = await harness.queue_manager.enqueue(
        tenant_id="t1", requesting_module="sentinel_agents", requesting_ref="alert-1", context={},
    )
    override_details = {
        "original_agent_proposal": {"action": "terminate"}, "human_override_action": {"action": "pause"},
        "override_reason": "termination too aggressive",
    }
    decision = await harness.decision_capture.capture(
        "t1", request.id, decision="override", decided_by="reviewer-a", override_details=override_details,
    )

    override = await harness.repository.get_override_for_decision(decision.id)
    assert override is not None
    assert override.original_agent_proposal == {"action": "terminate"}
    assert override.human_override_action == {"action": "pause"}

    override_events = [e for e in harness.auditability.events if e["event"] == "oversight_override"]
    assert len(override_events) == 1
    assert override_events[0]["original_agent_proposal"] == {"action": "terminate"}


async def test_reject_does_not_create_override_record(harness):
    request = await harness.queue_manager.enqueue(
        tenant_id="t1", requesting_module="guardrails", requesting_ref="ref-1", context={},
    )
    decision = await harness.decision_capture.capture("t1", request.id, decision="rejected", decided_by="reviewer-a")
    assert await harness.repository.get_override_for_decision(decision.id) is None


async def test_decide_missing_request_raises(harness):
    with pytest.raises(RequestNotFoundError):
        await harness.decision_capture.capture("t1", "does-not-exist", decision="approved", decided_by="reviewer-a")


async def test_decide_already_decided_request_raises(harness):
    request = await harness.queue_manager.enqueue(
        tenant_id="t1", requesting_module="guardrails", requesting_ref="ref-1", context={},
    )
    await harness.decision_capture.capture("t1", request.id, decision="approved", decided_by="reviewer-a")
    with pytest.raises(RequestNotDecidableError):
        await harness.decision_capture.capture("t1", request.id, decision="rejected", decided_by="reviewer-b")


async def test_decide_after_claim_works(harness):
    request = await harness.queue_manager.enqueue(
        tenant_id="t1", requesting_module="guardrails", requesting_ref="ref-1", context={},
    )
    await harness.queue_manager.claim("t1", request.id, "reviewer-a")
    decision = await harness.decision_capture.capture("t1", request.id, decision="approved", decided_by="reviewer-a")
    assert decision.decision.value == "approved"
