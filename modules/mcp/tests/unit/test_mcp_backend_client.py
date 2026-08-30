"""Tests for clients/mcp_backend_client.py -- JSON-RPC forwarding and the
per-server circuit breaker isolation this client's docstring claims."""
from __future__ import annotations

import httpx
import pytest
import respx

from mcp_gateway.clients.mcp_backend_client import CircuitBreakerError, MCPBackendHTTPClient
from mcp_gateway.core.domain import JsonRpcRequest


@respx.mock
async def test_send_relays_a_successful_response():
    respx.post("http://server-a.example/rpc").mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"tools": []}})
    )
    client = MCPBackendHTTPClient()

    response = await client.send(
        "http://server-a.example/rpc", JsonRpcRequest(jsonrpc="2.0", method="tools/list", params=None, id=1),
    )

    assert response.result == {"tools": []}
    assert response.error is None


@respx.mock
async def test_list_tools_returns_the_result_tools_array():
    respx.post("http://server-a.example/rpc").mock(
        return_value=httpx.Response(200, json={
            "jsonrpc": "2.0", "id": "tools-list",
            "result": {"tools": [{"name": "search", "description": "", "inputSchema": {}}]},
        })
    )
    client = MCPBackendHTTPClient()

    tools = await client.list_tools("http://server-a.example/rpc")

    assert len(tools) == 1
    assert tools[0]["name"] == "search"


@respx.mock
async def test_a_struggling_server_never_trips_a_different_servers_breaker():
    respx.post("http://server-a.example/rpc").mock(return_value=httpx.Response(503))
    respx.post("http://server-b.example/rpc").mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
    )
    client = MCPBackendHTTPClient(fail_max=2)

    for _ in range(6):
        with pytest.raises((httpx.HTTPStatusError, CircuitBreakerError)):
            await client.send(
                "http://server-a.example/rpc", JsonRpcRequest(jsonrpc="2.0", method="tools/list", params=None, id=1),
            )

    # Server A's breaker is open by now; server B must be entirely unaffected.
    response = await client.send(
        "http://server-b.example/rpc", JsonRpcRequest(jsonrpc="2.0", method="tools/list", params=None, id=1),
    )
    assert response.result == {"ok": True}
