"""Registry Service (LLD §2 sub-components): CRUD for registered MCP
servers — the "internal server marketplace" itself. Registering a server
here is what makes it usable platform-wide with no caller-side code
change (see the module README's "Design notes vs. the LLD").
"""
from __future__ import annotations

from mcp_gateway.core.domain import McpServerNotFoundError, McpServerRecord, new_id
from mcp_gateway.core.ports import MCPGatewayRepository


class RegistryService:
    def __init__(self, repository: MCPGatewayRepository) -> None:
        self._repository = repository

    async def register(self, *, tenant_id: str, name: str, description: str, base_url: str) -> McpServerRecord:
        record = McpServerRecord(id=new_id(), tenant_id=tenant_id, name=name, description=description, base_url=base_url)
        return await self._repository.create_server(record)

    async def get(self, server_id: str) -> McpServerRecord:
        record = await self._repository.get_server(server_id)
        if record is None:
            raise McpServerNotFoundError(server_id)
        return record

    async def list(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[McpServerRecord], int]:
        return await self._repository.list_servers(tenant_id=tenant_id, limit=limit, offset=offset)
