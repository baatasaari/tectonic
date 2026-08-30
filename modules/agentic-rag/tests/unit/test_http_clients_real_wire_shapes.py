"""Ticket #82 (Phase 2 support-agent slice): standing this module up
against real running peers for the first time surfaced that
`HTTPVectorDBClient.search()` and `HTTPLLMGatewayClient`'s two methods
each posted an invented request shape/path never validated against the
real peer -- invisible before because every prior test stubbed these
calls. These tests pin each client's real wire contract (path, body,
headers, response field names) using respx rather than a stub server, so
a future accidental revert back to the invented shape fails immediately.
See http_clients.py's own updated docstrings for the full reasoning."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from agentic_rag.clients.http_clients import HTTPLLMGatewayClient, HTTPVectorDBClient
from agentic_rag.core.domain import Provenance, RetrievalSource, RetrievedItem

pytestmark = pytest.mark.asyncio


@respx.mock
async def test_vector_db_client_calls_the_real_query_endpoint():
    route = respx.post("http://vdb.local/v1/vector-db/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "point-1", "score": 0.87,
                        "payload": {"content": "returns within 30 days", "document_id": "doc-1"},
                    },
                ],
            },
        )
    )
    client = HTTPVectorDBClient("http://vdb.local")

    items = await client.search(query="what's your return policy?", scope=["policy"], tenant_id="acme")

    assert items == [
        RetrievedItem(
            content="returns within 30 days",
            source=RetrievalSource.VECTOR_DB,
            provenance=Provenance(source_document="doc-1", location="point-1"),
            retrieval_score=0.87,
        )
    ]
    body = json.loads(route.calls.last.request.content)
    assert body == {"tenant_id": "acme", "text": "what's your return policy?", "filters": {}}


@respx.mock
async def test_llm_gateway_client_assess_groundedness_calls_the_real_chat_completions_endpoint():
    route = respx.post("http://llm-gw.local/v1/llm-gateway/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "c1", "object": "chat.completion", "model": "rag-groundedness-critic",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps({"score": 0.9, "gaps": ""})}, "finish_reason": "stop"}],
                "provider_used": "mock", "cache_hit": False, "cost": 0.0,
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )
    )
    client = HTTPLLMGatewayClient("http://llm-gw.local", default_virtual_key="vk-1")

    assessment = await client.assess_groundedness(
        query="what's your return policy?",
        items=[RetrievedItem(content="x", source=RetrievalSource.VECTOR_DB, provenance=Provenance(source_document="doc-1"))],
        tenant_id="acme",
    )

    assert assessment.score == 0.9
    assert assessment.gaps == ""
    request = route.calls.last.request
    assert request.headers["X-Virtual-Key"] == "vk-1"
    assert request.headers["X-Tenant-Id"] == "acme"
    body = json.loads(request.content)
    assert body["model"] == "rag-groundedness-critic"


@respx.mock
async def test_llm_gateway_client_reformulate_calls_the_real_chat_completions_endpoint():
    respx.post("http://llm-gw.local/v1/llm-gateway/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "c1", "object": "chat.completion", "model": "rag-query-reformulator",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps({"revised_query": "return policy details"})}, "finish_reason": "stop"}],
                "provider_used": "mock", "cache_hit": False, "cost": 0.0,
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )
    )
    client = HTTPLLMGatewayClient("http://llm-gw.local", default_virtual_key="vk-1")

    revised = await client.reformulate(query="return policy?", gaps="too vague", tenant_id="acme")

    assert revised == "return policy details"
