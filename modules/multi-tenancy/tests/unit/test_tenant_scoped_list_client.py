"""Tests for clients/tenant_scoped_list_client.py -- the one generic
client reused against any platform module following the shared
`?tenant_id=X` -> `{"items": [...]}` list contract."""
from __future__ import annotations

import httpx
import respx

from multi_tenancy.clients.tenant_scoped_list_client import HTTPTenantScopedListClient


@respx.mock
async def test_list_tenant_scoped_items_returns_the_items_array():
    route = respx.get("http://agent-cards.local/v1/agent-cards").mock(
        return_value=httpx.Response(200, json={
            "items": [{"id": "c1", "tenant_id": "acme"}], "total": 1, "limit": 200, "offset": 0,
        })
    )
    client = HTTPTenantScopedListClient("http://agent-cards.local", "/v1/agent-cards", audience="agent-cards")

    items = await client.list_tenant_scoped_items(tenant_id="acme")

    assert items == [{"id": "c1", "tenant_id": "acme"}]
    sent = route.calls.last.request
    assert "tenant_id=acme" in str(sent.url)


@respx.mock
async def test_list_tenant_scoped_items_returns_empty_list_by_default():
    respx.get("http://agent-cards.local/v1/agent-cards").mock(
        return_value=httpx.Response(200, json={"items": [], "total": 0, "limit": 200, "offset": 0})
    )
    client = HTTPTenantScopedListClient("http://agent-cards.local", "/v1/agent-cards", audience="agent-cards")

    items = await client.list_tenant_scoped_items(tenant_id="acme")

    assert items == []
