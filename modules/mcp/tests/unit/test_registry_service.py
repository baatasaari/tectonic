"""Tests for core/registry_service.py -- the marketplace CRUD."""
from __future__ import annotations

import pytest

from mcp_gateway.core.domain import McpServerNotFoundError


async def test_register_creates_an_active_server(harness):
    server = await harness.registry_service.register(
        tenant_id="acme", name="search-tools", description="web search", base_url="http://mcp.example/search",
    )

    assert server.tenant_id == "acme"
    assert server.status.value == "active"


async def test_get_raises_for_an_unknown_server(harness):
    with pytest.raises(McpServerNotFoundError):
        await harness.registry_service.get("does-not-exist")


async def test_list_filters_by_tenant(harness):
    await harness.registry_service.register(tenant_id="acme", name="s1", description="", base_url="http://a")
    await harness.registry_service.register(tenant_id="globex", name="s2", description="", base_url="http://b")

    servers, total = await harness.registry_service.list(tenant_id="acme")

    assert total == 1
    assert servers[0].tenant_id == "acme"


async def test_list_paginates(harness):
    for i in range(5):
        await harness.registry_service.register(tenant_id="acme", name=f"s{i}", description="", base_url=f"http://{i}")

    page1, total1 = await harness.registry_service.list(limit=2, offset=0)
    page2, total2 = await harness.registry_service.list(limit=2, offset=2)

    assert total1 == total2 == 5
    assert len(page1) == 2
    assert len(page2) == 2
    assert {s.id for s in page1}.isdisjoint({s.id for s in page2})
