"""In-memory fakes for unit tests (LLD "Deployability and testability
contract")."""
from __future__ import annotations

from typing import Any

from mcp_gateway.core.domain import (
    AccessPolicyRecord,
    JsonRpcRequest,
    JsonRpcResponse,
    McpServerRecord,
    McpToolRecord,
)


class InMemoryMCPGatewayRepository:
    def __init__(self) -> None:
        self.servers: dict[str, McpServerRecord] = {}
        self.tools: dict[str, list[McpToolRecord]] = {}
        self.access_policies: dict[tuple[str, str], AccessPolicyRecord] = {}

    async def create_server(self, record: McpServerRecord) -> McpServerRecord:
        self.servers[record.id] = record
        return record

    async def get_server(self, server_id: str) -> McpServerRecord | None:
        return self.servers.get(server_id)

    async def list_servers(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[McpServerRecord], int]:
        results = list(self.servers.values())
        if tenant_id is not None:
            results = [s for s in results if s.tenant_id == tenant_id]
        results = sorted(results, key=lambda s: s.created_at)
        return results[offset:offset + limit], len(results)

    async def replace_tools(self, server_id: str, tools: list[McpToolRecord]) -> None:
        self.tools[server_id] = list(tools)

    async def list_tools(self, server_id: str) -> list[McpToolRecord]:
        return list(self.tools.get(server_id, []))

    async def upsert_access_policy(self, record: AccessPolicyRecord) -> AccessPolicyRecord:
        self.access_policies[(record.server_id, record.tenant_id)] = record
        return record

    async def get_access_policy(self, server_id: str, tenant_id: str) -> AccessPolicyRecord | None:
        return self.access_policies.get((server_id, tenant_id))


class StubMCPBackendClient:
    def __init__(
        self, *, tools: list[dict[str, Any]] | None = None, response: JsonRpcResponse | None = None,
    ) -> None:
        self.calls: list[dict] = []
        self._tools = tools if tools is not None else []
        self._response = response

    async def send(self, base_url: str, request: JsonRpcRequest) -> JsonRpcResponse:
        self.calls.append({"base_url": base_url, "request": request})
        if self._response is not None:
            return self._response
        return JsonRpcResponse(jsonrpc="2.0", id=request.id, result={"ok": True})

    async def list_tools(self, base_url: str) -> list[dict[str, Any]]:
        self.calls.append({"base_url": base_url, "method": "tools/list"})
        return self._tools


__all__ = ["InMemoryMCPGatewayRepository", "StubMCPBackendClient"]
