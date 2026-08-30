"""Phase 2 assessment follow-up: every one of this module's peer HTTP
clients was posting an invented request shape and/or reading an invented
response shape -- never validated against a real running peer on THIS
module's own direct (non-`workflow_routing`) turn-handling path, since the
ticket #82 product-slice test only ever exercised the `workflow_routing`
path (Workflow Engine's own already-fixed clients). These tests pin each
client's real wire contract (path, body, headers, response field names)
against the peer's own actual route/schema, using respx rather than a stub
server, so a future accidental revert back to an invented shape fails
immediately -- the same reference pattern Workflow Engine's own
`test_http_clients_real_wire_shapes.py` established for this identical
problem (ticket #82).
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from conversational_engine.clients.http_clients import (
    HTTPGuardrailsClient,
    HTTPHumanOversightClient,
    HTTPLLMGatewayClient,
    HTTPLongTermMemoryClient,
    HTTPObservabilityClient,
)

pytestmark = pytest.mark.asyncio


@respx.mock
async def test_llm_gateway_stream_complete_calls_the_real_chat_completions_endpoint():
    route = respx.post("http://llm-gw.local/v1/llm-gateway/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "c1", "object": "chat.completion", "model": "default",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello there"}, "finish_reason": "stop"}],
                "provider_used": "mock", "cache_hit": False, "cost": 0.001,
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            },
        )
    )
    client = HTTPLLMGatewayClient("http://llm-gw.local", default_virtual_key="vk-1")

    chunks = [c async for c in client.stream_complete(
        prompt_context={"persona_name": "default", "message": "hi"}, tenant_id="acme", trace_id="trace-1",
    )]

    assert chunks == ["hello there"]
    request = route.calls.last.request
    assert request.headers["X-Virtual-Key"] == "vk-1"
    assert request.headers["X-Tenant-Id"] == "acme"
    assert request.headers["X-Trace-Id"] == "trace-1"
    body = json.loads(request.content)
    assert body["model"] == "default"
    assert json.loads(body["messages"][0]["content"])["message"] == "hi"


@respx.mock
async def test_llm_gateway_classify_degrades_to_empty_on_unparseable_response():
    respx.post("http://llm-gw.local/v1/llm-gateway/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "c1", "object": "chat.completion", "model": "classification",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "not json"}, "finish_reason": "stop"}],
                "provider_used": "mock", "cache_hit": False, "cost": 0.0,
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )
    )
    client = HTTPLLMGatewayClient("http://llm-gw.local")

    result = await client.classify(text="ugh", taxonomy=["calm", "frustrated"], tenant_id="acme")

    assert result == {}


@respx.mock
async def test_guardrails_check_calls_the_real_check_endpoint_and_maps_the_real_response():
    route = respx.post("http://gr.local/v1/guardrails/check").mock(
        return_value=httpx.Response(
            200, json={"decision": "block", "violation_category": "pii", "redacted_text": None, "checks_run": ["pii_detection"]},
        )
    )
    client = HTTPGuardrailsClient("http://gr.local")

    allowed, detail = await client.check(content={"output": "some text"}, policy_profile="default", tenant_id="acme")

    assert allowed is False
    assert detail["violation_category"] == "pii"
    request = route.calls.last.request
    assert request.headers["X-Tenant-Id"] == "acme"
    body = json.loads(request.content)
    assert body == {"text": "some text", "stage": "output"}


@respx.mock
async def test_human_oversight_request_handoff_posts_to_the_real_route_with_the_resume_contract():
    route = respx.post("http://ho.local/v1/human-oversight/requests").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": "req-1", "tenant_id": "acme", "requesting_module": "conversational_engine",
                "requesting_ref": "session-1", "context": {}, "priority": "medium",
                "status": "pending", "claimed_by": None,
                "created_at": "2026-01-01T00:00:00Z", "expires_at": "2026-01-02T00:00:00Z",
            },
        )
    )
    client = HTTPHumanOversightClient("http://ho.local")

    ref = await client.request_handoff(
        session_id="session-1", trigger_reason="emotion", context={"emotion_score": 0.9}, tenant_id="acme",
    )

    assert ref == "req-1"
    body = json.loads(route.calls.last.request.content)
    assert body["requesting_module"] == "conversational_engine"
    assert body["requesting_ref"] == "session-1"
    assert body["context"]["trigger_reason"] == "emotion"


@respx.mock
async def test_long_term_memory_recall_calls_the_real_query_endpoint():
    route = respx.post("http://ltm.local/v1/long-term-memory/query").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "item": {
                        "id": "m1", "scope": "user:u1", "memory_type": "episodic", "content": "prefers email",
                        "visibility_policy_ref": "", "vector_ref": None, "graph_ref": None, "status": "active",
                        "relevance_score": 1.0, "created_at": "2026-01-01T00:00:00Z", "last_accessed_at": "2026-01-01T00:00:00Z",
                    },
                    "score": 0.9,
                }
            ],
        )
    )
    client = HTTPLongTermMemoryClient("http://ltm.local")

    result = await client.recall_identity_context(user_ref="u1", tenant_id="acme", query="how do I contact you")

    assert result == {"items": [{"content": "prefers email", "memory_type": "episodic", "score": 0.9}]}
    body = json.loads(route.calls.last.request.content)
    assert body["scope"] == "user:u1"
    assert body["query"] == "how do I contact you"
    assert route.calls.last.request.headers["X-Tenant-Id"] == "acme"


@respx.mock
async def test_long_term_memory_recall_returns_none_for_an_empty_result():
    respx.post("http://ltm.local/v1/long-term-memory/query").mock(return_value=httpx.Response(200, json=[]))
    client = HTTPLongTermMemoryClient("http://ltm.local")

    result = await client.recall_identity_context(user_ref="u1", tenant_id="acme", query="hi")

    assert result is None


@respx.mock
async def test_observability_emit_calls_the_real_ingest_endpoint():
    route = respx.post("http://obs.local/v1/observability/ingest").mock(return_value=httpx.Response(201, json={}))
    client = HTTPObservabilityClient("http://obs.local")

    await client.emit({"event_type": "conversation.turn.completed", "session_id": "s1", "tenant_id": "acme", "trace_id": "t1"})

    body = json.loads(route.calls.last.request.content)
    assert body["tenant_id"] == "acme"
    assert body["trace_id"] == "t1"
    assert body["spans"][0]["name"] == "conversation.turn.completed"
    assert body["spans"][0]["attributes"]["session_id"] == "s1"


@respx.mock
async def test_observability_emit_never_raises_on_a_peer_failure():
    respx.post("http://obs.local/v1/observability/ingest").mock(return_value=httpx.Response(500))
    client = HTTPObservabilityClient("http://obs.local")

    await client.emit({"event_type": "conversation.turn.completed"})  # must not raise
