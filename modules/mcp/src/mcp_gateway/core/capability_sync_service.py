"""Capability Sync Service (LLD §2 sub-components): refreshes a
registered server's cached tool list by calling its own real `tools/list`
method — always a wholesale replace, never a merge, so the cache never
drifts into showing a tool the backend has actually removed.
"""
from __future__ import annotations

from mcp_gateway.core.domain import McpServerNotFoundError, McpToolRecord, new_id
from mcp_gateway.core.ports import MCPBackendClient, MCPGatewayRepository


class CapabilitySyncService:
    def __init__(self, repository: MCPGatewayRepository, backend: MCPBackendClient) -> None:
        self._repository = repository
        self._backend = backend

    async def sync(self, server_id: str) -> list[McpToolRecord]:
        server = await self._repository.get_server(server_id)
        if server is None:
            raise McpServerNotFoundError(server_id)

        raw_tools = await self._backend.list_tools(server.base_url)
        tools = [
            McpToolRecord(
                id=new_id(), server_id=server_id, name=t.get("name", ""), description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            )
            for t in raw_tools
        ]
        await self._repository.replace_tools(server_id, tools)
        return tools
