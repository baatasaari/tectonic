"""Abstract ports this module depends on: persistence and the backend MCP
client (the outbound call to a registered server's real endpoint).
"""
from __future__ import annotations

from typing import Any, Protocol

from mcp_gateway.core.domain import (
    AccessPolicyRecord,
    JsonRpcRequest,
    JsonRpcResponse,
    McpServerRecord,
    McpToolRecord,
)


class MCPGatewayRepository(Protocol):
    async def create_server(self, record: McpServerRecord) -> McpServerRecord: ...

    async def get_server(self, server_id: str) -> McpServerRecord | None: ...

    async def list_servers(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[McpServerRecord], int]: ...

    async def replace_tools(self, server_id: str, tools: list[McpToolRecord]) -> None:
        """Wholesale replace — a sync always reflects the backend's current
        `tools/list` response exactly, not a merge of old and new."""
        ...

    async def list_tools(self, server_id: str) -> list[McpToolRecord]: ...

    async def upsert_access_policy(self, record: AccessPolicyRecord) -> AccessPolicyRecord: ...

    async def get_access_policy(self, server_id: str, tenant_id: str) -> AccessPolicyRecord | None: ...


class MCPBackendClient(Protocol):
    async def send(self, base_url: str, request: JsonRpcRequest) -> JsonRpcResponse:
        """Forwards a JSON-RPC 2.0 request to a registered server's real
        endpoint and returns its response, relayed unmodified."""
        ...

    async def list_tools(self, base_url: str) -> list[dict[str, Any]]:
        """Calls the backend's own `tools/list` method for capability sync.
        Returns the raw `result.tools` array (each a dict with at least
        `name`/`description`/`inputSchema`, per the MCP spec)."""
        ...
