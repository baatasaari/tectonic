"""Tests for clients/llm_gateway_client.py -- calls LLM Gateway's real
GET /admin/virtual-keys + GET /admin/budgets/{id} endpoint shapes and
dedupes budget_policy_refs shared across multiple virtual keys."""
from __future__ import annotations

import httpx
import respx

from finops.clients.llm_gateway_client import HTTPLLMGatewayClient


@respx.mock
async def test_tenant_spend_sums_current_spend_across_distinct_budget_policies():
    respx.get("http://llmgw.local/v1/llm-gateway/admin/virtual-keys").mock(
        return_value=httpx.Response(200, json={
            "items": [
                {"id": "vk1", "budget_policy_ref": "bp1"},
                {"id": "vk2", "budget_policy_ref": "bp2"},
            ],
        })
    )
    respx.get("http://llmgw.local/v1/llm-gateway/admin/budgets/bp1").mock(
        return_value=httpx.Response(200, json={"id": "bp1", "current_spend": 12.5})
    )
    respx.get("http://llmgw.local/v1/llm-gateway/admin/budgets/bp2").mock(
        return_value=httpx.Response(200, json={"id": "bp2", "current_spend": 7.5})
    )
    client = HTTPLLMGatewayClient("http://llmgw.local")

    spend = await client.tenant_spend("acme")

    assert spend == 20.0


@respx.mock
async def test_tenant_spend_dedupes_a_budget_policy_shared_by_multiple_virtual_keys():
    respx.get("http://llmgw.local/v1/llm-gateway/admin/virtual-keys").mock(
        return_value=httpx.Response(200, json={
            "items": [
                {"id": "vk1", "budget_policy_ref": "bp1"},
                {"id": "vk2", "budget_policy_ref": "bp1"},
            ],
        })
    )
    route = respx.get("http://llmgw.local/v1/llm-gateway/admin/budgets/bp1").mock(
        return_value=httpx.Response(200, json={"id": "bp1", "current_spend": 30.0})
    )
    client = HTTPLLMGatewayClient("http://llmgw.local")

    spend = await client.tenant_spend("acme")

    assert spend == 30.0
    assert route.call_count == 1


@respx.mock
async def test_tenant_spend_is_zero_when_the_tenant_has_no_virtual_keys():
    respx.get("http://llmgw.local/v1/llm-gateway/admin/virtual-keys").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    client = HTTPLLMGatewayClient("http://llmgw.local")

    spend = await client.tenant_spend("acme")

    assert spend == 0.0
