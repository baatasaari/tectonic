"""Tests for core/rpc_gateway.py -- the `/v1/a2a/rpc` wire surface:
`message/send`, `tasks/get`, `tasks/cancel`, and an unknown method."""
from __future__ import annotations

from a2a_gateway.core.domain import A2AAccessPolicyRecord, new_id


async def test_message_send_returns_a_jsonrpc_error_when_no_policy_exists(harness):
    response = await harness.rpc_gateway.handle(
        method="message/send", params={"skill_id": "summarize", "message": {}}, id=1,
        tenant_id="acme", caller_agent_id="peer-1", peer_agent_url="http://peer",
    )

    assert response.error is not None
    assert response.error["code"] == -32001
    assert response.result is None


async def test_message_send_returns_a_jsonrpc_error_for_an_unknown_skill(harness):
    await harness.repository.upsert_access_policy(
        A2AAccessPolicyRecord(id=new_id(), caller_agent_id="peer-1", tenant_id="acme", allowed_skills=None)
    )

    response = await harness.rpc_gateway.handle(
        method="message/send", params={"skill_id": "not-a-real-skill", "message": {}}, id=1,
        tenant_id="acme", caller_agent_id="peer-1", peer_agent_url="http://peer",
    )

    assert response.error is not None
    assert response.error["code"] == -32002


async def test_message_send_accepts_and_returns_the_task(harness):
    await harness.repository.upsert_access_policy(
        A2AAccessPolicyRecord(id=new_id(), caller_agent_id="peer-1", tenant_id="acme", allowed_skills=None)
    )

    response = await harness.rpc_gateway.handle(
        method="message/send", params={"skill_id": "summarize", "message": {"text": "hi"}}, id=1,
        tenant_id="acme", caller_agent_id="peer-1", peer_agent_url="http://peer",
    )

    assert response.error is None
    assert response.result["status"] == "working"
    assert "task_id" in response.result


async def test_tasks_get_returns_not_found_for_an_unknown_task(harness):
    response = await harness.rpc_gateway.handle(
        method="tasks/get", params={"task_id": "does-not-exist"}, id=1,
        tenant_id="acme", caller_agent_id="peer-1", peer_agent_url="http://peer",
    )

    assert response.error is not None
    assert response.error["code"] == -32003


async def test_tasks_get_returns_the_current_status(harness):
    await harness.repository.upsert_access_policy(
        A2AAccessPolicyRecord(id=new_id(), caller_agent_id="peer-1", tenant_id="acme", allowed_skills=None)
    )
    sent = await harness.rpc_gateway.handle(
        method="message/send", params={"skill_id": "summarize", "message": {}}, id=1,
        tenant_id="acme", caller_agent_id="peer-1", peer_agent_url="http://peer",
    )

    response = await harness.rpc_gateway.handle(
        method="tasks/get", params={"task_id": sent.result["task_id"]}, id=2,
        tenant_id="acme", caller_agent_id="peer-1", peer_agent_url="http://peer",
    )

    assert response.result["task_id"] == sent.result["task_id"]


async def test_tasks_cancel_updates_status_to_canceled(harness):
    await harness.repository.upsert_access_policy(
        A2AAccessPolicyRecord(id=new_id(), caller_agent_id="peer-1", tenant_id="acme", allowed_skills=None)
    )
    sent = await harness.rpc_gateway.handle(
        method="message/send", params={"skill_id": "summarize", "message": {}}, id=1,
        tenant_id="acme", caller_agent_id="peer-1", peer_agent_url="http://peer",
    )

    response = await harness.rpc_gateway.handle(
        method="tasks/cancel", params={"task_id": sent.result["task_id"]}, id=2,
        tenant_id="acme", caller_agent_id="peer-1", peer_agent_url="http://peer",
    )

    assert response.result["status"] == "canceled"


async def test_an_unknown_method_returns_method_not_found(harness):
    response = await harness.rpc_gateway.handle(
        method="not/a-real-method", params={}, id=1,
        tenant_id="acme", caller_agent_id="peer-1", peer_agent_url="http://peer",
    )

    assert response.error is not None
    assert response.error["code"] == -32601
