"""Tests for core/delegation_service.py -- the outbound half: card-fetch
handshake, skill-match check, caching, and failure handling."""
from __future__ import annotations

import pytest

from a2a_gateway.core.domain import SkillNotAdvertisedError, TaskDirection, TaskStatus
from a2a_gateway.core.fakes import StubA2APeerClient


async def test_delegate_rejects_a_skill_the_target_does_not_advertise(harness_factory):
    peer = StubA2APeerClient(card={"name": "peer", "description": "", "url": "http://peer", "skills": []})
    harness = harness_factory(peer_client=peer)

    with pytest.raises(SkillNotAdvertisedError):
        await harness.delegation_service.delegate(
            tenant_id="acme", target_agent_url="http://peer", skill_id="summarize", input_message={},
        )
    assert not any(c["op"] == "send_message" for c in peer.calls), "must fail fast locally, never reach the peer"


async def test_delegate_sends_and_persists_a_completed_task(harness_factory):
    peer = StubA2APeerClient(
        card={"name": "peer", "description": "", "url": "http://peer", "skills": [{"id": "summarize", "name": "Summarize"}]},
        send_result={"status": "completed", "artifacts": [{"summary": "done"}]},
    )
    harness = harness_factory(peer_client=peer)

    task = await harness.delegation_service.delegate(
        tenant_id="acme", target_agent_url="http://peer", skill_id="summarize", input_message={"text": "hello"},
    )

    assert task.direction == TaskDirection.OUTBOUND
    assert task.status == TaskStatus.COMPLETED
    assert task.output_artifacts == [{"summary": "done"}]
    persisted = await harness.repository.get_task(task.id)
    assert persisted.status == TaskStatus.COMPLETED


async def test_delegate_marks_the_task_failed_when_the_peer_call_raises(harness_factory):
    peer = StubA2APeerClient(
        card={"name": "peer", "description": "", "url": "http://peer", "skills": [{"id": "summarize", "name": "Summarize"}]},
        send_error=RuntimeError("peer is unreachable"),
    )
    harness = harness_factory(peer_client=peer)

    task = await harness.delegation_service.delegate(
        tenant_id="acme", target_agent_url="http://peer", skill_id="summarize", input_message={},
    )

    assert task.status == TaskStatus.FAILED
    assert "unreachable" in task.error


async def test_delegate_caches_the_card_and_does_not_refetch_on_a_second_call(harness_factory):
    peer = StubA2APeerClient(
        card={"name": "peer", "description": "", "url": "http://peer", "skills": [{"id": "summarize", "name": "Summarize"}]},
    )
    harness = harness_factory(peer_client=peer)

    await harness.delegation_service.delegate(tenant_id="acme", target_agent_url="http://peer", skill_id="summarize", input_message={})
    await harness.delegation_service.delegate(tenant_id="acme", target_agent_url="http://peer", skill_id="summarize", input_message={})

    fetch_calls = [c for c in peer.calls if c["op"] == "fetch_agent_card"]
    assert len(fetch_calls) == 1, "a cached, unexpired card must not trigger a second fetch"
