from datetime import UTC, datetime, timedelta

import pytest

from human_oversight.core.domain import (
    RequestNotClaimableError,
    RequestNotFoundError,
    RequestStatus,
)


async def test_enqueue_creates_pending_request(harness):
    request = await harness.queue_manager.enqueue(
        tenant_id="t1", requesting_module="workflow_engine", requesting_ref="wf-1:approval-1", context={"foo": "bar"},
    )
    assert request.status == RequestStatus.PENDING
    assert request.context == {"foo": "bar"}


async def test_enqueue_uses_default_timeout_when_not_specified(harness):
    request = await harness.queue_manager.enqueue(
        tenant_id="t1", requesting_module="workflow_engine", requesting_ref="ref-1", context={},
    )
    expected = request.created_at + timedelta(seconds=harness.default_timeout_seconds)
    assert abs((request.expires_at - expected).total_seconds()) < 2


async def test_enqueue_respects_custom_timeout(harness):
    request = await harness.queue_manager.enqueue(
        tenant_id="t1", requesting_module="guardrails", requesting_ref="ref-1", context={}, timeout_seconds=60,
    )
    assert (request.expires_at - request.created_at).total_seconds() <= 61


async def test_claim_transitions_to_claimed(harness):
    request = await harness.queue_manager.enqueue(
        tenant_id="t1", requesting_module="sentinel_agents", requesting_ref="ref-1", context={},
    )
    claimed = await harness.queue_manager.claim("t1", request.id, "reviewer-a")
    assert claimed.status == RequestStatus.CLAIMED
    assert claimed.claimed_by == "reviewer-a"


async def test_claim_missing_request_raises(harness):
    with pytest.raises(RequestNotFoundError):
        await harness.queue_manager.claim("t1", "does-not-exist", "reviewer-a")


async def test_claim_already_claimed_request_raises(harness):
    request = await harness.queue_manager.enqueue(
        tenant_id="t1", requesting_module="guardrails", requesting_ref="ref-1", context={},
    )
    await harness.queue_manager.claim("t1", request.id, "reviewer-a")
    with pytest.raises(RequestNotClaimableError):
        await harness.queue_manager.claim("t1", request.id, "reviewer-b")


async def test_sweep_expired_marks_overdue_requests(harness):
    request = await harness.queue_manager.enqueue(
        tenant_id="t1", requesting_module="guardrails", requesting_ref="ref-1", context={}, timeout_seconds=1,
    )
    stale = request
    stale.expires_at = datetime.now(UTC) - timedelta(seconds=10)
    await harness.repository.update_request(stale)

    expired = await harness.queue_manager.sweep_expired("t1")
    assert len(expired) == 1
    assert expired[0].status == RequestStatus.EXPIRED


async def test_sweep_expired_leaves_fresh_requests_alone(harness):
    await harness.queue_manager.enqueue(
        tenant_id="t1", requesting_module="guardrails", requesting_ref="ref-1", context={}, timeout_seconds=86400,
    )
    expired = await harness.queue_manager.sweep_expired("t1")
    assert expired == []
