"""Tests for clients/llm_gateway_client.py -- calls LLM Gateway's real
POST /v1/llm-gateway/chat/completions endpoint shape."""
from __future__ import annotations

import httpx
import respx

from promptops.clients.llm_gateway_client import HTTPLLMGatewayClient


@respx.mock
async def test_generate_returns_the_first_choice_message_content():
    route = respx.post("http://llmgw.local/v1/llm-gateway/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "id": "cmpl-1", "object": "chat.completion", "model": "gpt-4o-mini",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "An improved template."}, "finish_reason": "stop"}],
            "provider_used": "openai", "cache_hit": False, "cost": 0.001, "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        })
    )
    client = HTTPLLMGatewayClient("http://llmgw.local")

    result = await client.generate(tenant_id="acme", model="gpt-4o-mini", prompt="improve this template")

    assert result == "An improved template."
    sent = route.calls.last.request
    assert sent.headers["X-Tenant-Id"] == "acme"
