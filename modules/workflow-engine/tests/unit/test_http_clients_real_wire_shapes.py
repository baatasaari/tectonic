"""Ticket #82 (Phase 2 support-agent slice): every one of this module's
pre-existing peer HTTP clients (LLM Gateway, Human Oversight, Tool
Orchestration, Guardrails) was posting an invented request shape and/or
reading an invented response shape -- never validated against a real
running peer before this ticket stood one up for the first time. These
tests pin each client's real wire contract (path, body, headers, response
field names) against the peer's own actual route/schema, using respx
rather than a stub server, so a future accidental revert back to the
invented shape fails immediately."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from workflow_engine.clients.http_clients import (
    HTTPGuardrailsClient,
    HTTPHumanOversightClient,
    HTTPLLMGatewayClient,
    HTTPToolOrchestrationClient,
)

pytestmark = pytest.mark.asyncio


@respx.mock
async def test_llm_gateway_client_calls_the_real_chat_completions_endpoint():
    route = respx.post("http://llm-gw.local/v1/llm-gateway/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "c1", "object": "chat.completion", "model": "support-agent-v1",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}],
                "provider_used": "mock", "cache_hit": False, "cost": 0.001,
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            },
        )
    )
    client = HTTPLLMGatewayClient("http://llm-gw.local", default_virtual_key="vk-1")

    response, confidence = await client.complete(
        agent_ref="support-agent-v1", prompt_context={"message": "hi"}, tenant_id="acme", trace_id="trace-1",
    )

    assert response == {"content": "hello"}
    assert confidence == 0.95
    request = route.calls.last.request
    assert request.headers["X-Virtual-Key"] == "vk-1"
    assert request.headers["X-Tenant-Id"] == "acme"
    body = json.loads(request.content)
    assert body["model"] == "support-agent-v1"
    assert json.loads(body["messages"][0]["content"]) == {"message": "hi"}


@respx.mock
async def test_human_oversight_client_posts_to_the_real_route_with_the_resume_contract():
    route = respx.post("http://ho.local/v1/human-oversight/requests").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": "req-1", "tenant_id": "acme", "requesting_module": "workflow_engine",
                "requesting_ref": "instance-1:approval-1", "context": {}, "priority": "medium",
                "status": "pending", "claimed_by": None,
                "created_at": "2026-01-01T00:00:00Z", "expires_at": "2026-01-02T00:00:00Z",
            },
        )
    )
    client = HTTPHumanOversightClient("http://ho.local")

    ref = await client.request_approval(
        approval_request_id="approval-1", step_execution_id="step-1", instance_id="instance-1",
        context={"refund_amount": 850}, tenant_id="acme",
    )

    assert ref == "req-1"
    body = json.loads(route.calls.last.request.content)
    assert body["requesting_module"] == "workflow_engine"
    assert body["requesting_ref"] == "instance-1:approval-1"
    assert body["tenant_id"] == "acme"


@respx.mock
async def test_tool_orchestration_client_posts_to_the_real_route_with_the_real_field_names():
    route = respx.post("http://to.local/v1/tool-orchestration/invoke").mock(
        return_value=httpx.Response(
            200, json={"result": {"status": "shipped"}, "status": "completed", "retry_count": 0, "latency_ms": 12.0},
        )
    )
    client = HTTPToolOrchestrationClient("http://to.local")

    result = await client.invoke(
        tool_ref="tool-uuid-1", arguments={"order_id": "A1029"}, agent_ref="order-lookup-agent",
        tenant_id="acme", trace_id="trace-1",
    )

    assert result == {"result": {"status": "shipped"}, "status": "completed", "retry_count": 0, "latency_ms": 12.0}
    request = route.calls.last.request
    assert request.headers["X-Tenant-Id"] == "acme"
    body = json.loads(request.content)
    assert body == {"tool_id": "tool-uuid-1", "parameters": {"order_id": "A1029"}, "agent_ref": "order-lookup-agent"}


@respx.mock
async def test_guardrails_client_posts_text_and_stage_and_maps_block_decision():
    route = respx.post("http://gr.local/v1/guardrails/check").mock(
        return_value=httpx.Response(
            200, json={"decision": "block", "violation_category": "policy_violation", "redacted_text": None, "checks_run": ["pii_detection"]},
        )
    )
    client = HTTPGuardrailsClient("http://gr.local")

    allowed, detail = await client.check(content={"output": "some text"}, policy_profile="default", tenant_id="acme")

    assert allowed is False
    assert detail["violation_category"] == "policy_violation"
    request = route.calls.last.request
    assert request.headers["X-Tenant-Id"] == "acme"
    body = json.loads(request.content)
    assert body == {"text": "some text", "stage": "output"}
