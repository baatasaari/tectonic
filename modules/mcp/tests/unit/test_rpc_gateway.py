"""Tests for core/rpc_gateway.py -- enforcement + forwarding together."""
from __future__ import annotations

import pytest

from mcp_gateway.core.domain import (
    AccessPolicyRecord,
    JsonRpcRequest,
    McpServerNotFoundError,
    new_id,
)


async def test_handle_raises_for_an_unregistered_server(harness):
    with pytest.raises(McpServerNotFoundError):
        await harness.rpc_gateway.handle(
            server_id="does-not-exist", tenant_id="acme",
            request=JsonRpcRequest(jsonrpc="2.0", method="tools/list", params=None, id=1),
        )


async def test_handle_returns_a_jsonrpc_error_when_no_policy_exists(harness):
    server = await harness.registry_service.register(
        tenant_id="acme", name="s", description="", base_url="http://backend.example",
    )

    response = await harness.rpc_gateway.handle(
        server_id=server.id, tenant_id="acme", request=JsonRpcRequest(jsonrpc="2.0", method="tools/list", params=None, id=1),
    )

    assert response.error is not None
    assert response.error["code"] == -32001
    assert response.result is None
    assert len(harness.backend.calls) == 0, "a denied request must never reach the backend"


async def test_handle_forwards_to_the_backend_when_authorized(harness):
    server = await harness.registry_service.register(
        tenant_id="acme", name="s", description="", base_url="http://backend.example",
    )
    await harness.repository.upsert_access_policy(
        AccessPolicyRecord(id=new_id(), server_id=server.id, tenant_id="acme", allowed_tools=None)
    )

    response = await harness.rpc_gateway.handle(
        server_id=server.id, tenant_id="acme", request=JsonRpcRequest(jsonrpc="2.0", method="tools/list", params=None, id=1),
    )

    assert response.result == {"ok": True}
    assert len(harness.backend.calls) == 1
    assert harness.backend.calls[0]["base_url"] == "http://backend.example"


async def test_handle_denies_a_tools_call_for_a_tool_not_in_the_allow_list(harness):
    server = await harness.registry_service.register(
        tenant_id="acme", name="s", description="", base_url="http://backend.example",
    )
    await harness.repository.upsert_access_policy(
        AccessPolicyRecord(id=new_id(), server_id=server.id, tenant_id="acme", allowed_tools=["search"])
    )

    response = await harness.rpc_gateway.handle(
        server_id=server.id, tenant_id="acme",
        request=JsonRpcRequest(jsonrpc="2.0", method="tools/call", params={"name": "delete_everything"}, id=1),
    )

    assert response.error is not None
    assert len(harness.backend.calls) == 0
