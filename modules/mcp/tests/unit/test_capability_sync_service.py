"""Tests for core/capability_sync_service.py -- wholesale replace, never a merge."""
from __future__ import annotations

import pytest

from mcp_gateway.core.domain import McpServerNotFoundError
from mcp_gateway.core.fakes import StubMCPBackendClient


async def test_sync_raises_for_an_unregistered_server(harness):
    with pytest.raises(McpServerNotFoundError):
        await harness.capability_sync_service.sync("does-not-exist")


async def test_sync_caches_the_backends_tool_list(harness_factory):
    backend = StubMCPBackendClient(tools=[
        {"name": "search", "description": "web search", "inputSchema": {"type": "object"}},
    ])
    harness = harness_factory(backend=backend)
    server = await harness.registry_service.register(tenant_id="acme", name="s", description="", base_url="http://backend")

    tools = await harness.capability_sync_service.sync(server.id)

    assert len(tools) == 1
    assert tools[0].name == "search"
    cached = await harness.repository.list_tools(server.id)
    assert len(cached) == 1


async def test_sync_wholesale_replaces_not_merges(harness_factory):
    backend = StubMCPBackendClient(tools=[{"name": "a", "description": "", "inputSchema": {}}])
    harness = harness_factory(backend=backend)
    server = await harness.registry_service.register(tenant_id="acme", name="s", description="", base_url="http://backend")
    await harness.capability_sync_service.sync(server.id)

    # The backend's tool list changed entirely between syncs.
    backend._tools = [{"name": "b", "description": "", "inputSchema": {}}]
    await harness.capability_sync_service.sync(server.id)

    cached = await harness.repository.list_tools(server.id)
    assert [t.name for t in cached] == ["b"], "the old tool 'a' must not survive a resync that no longer lists it"
