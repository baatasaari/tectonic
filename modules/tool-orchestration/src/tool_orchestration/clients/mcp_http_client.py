"""MCP Client Adapter (LLD stack table: "Model Context Protocol via the
official `mcp` Python SDK").

Implemented here as a generic JSON-RPC-2.0-over-HTTP client rather than a
hard dependency on the `mcp` package: JSON-RPC over a transport is MCP's
wire-level shape regardless of which transport variant a given server
speaks. Swapping in the official `mcp` SDK (stdio/SSE/streamable-HTTP
transports, capability negotiation, resource/prompt primitives beyond tool
calls) means implementing this same `MCPClientAdapter` Protocol against
it — same boundary Module 1 draws around ADK and Module 3 draws around
LiteLLM.

`ToolDefinition.mcp_server_ref` (LLD §3.1) is the only field the data model
gives us to locate a tool's server. This adapter treats it as a URL
directly when it looks like one (the common case for internal MCP servers
registered with their own address); for a symbolic ref pointing at a
server this deployment knows about under a friendlier name, register an
alias via `set_server_aliases`.

Deliberately excluded from this platform's service-to-service JWT auth
(security/jwt_auth.py): this adapter calls arbitrary third-party MCP tool
servers, not a platform peer module — those servers have their own
(possibly nonexistent, possibly entirely different) auth scheme, and
attaching this platform's shared-secret-signed token to them would be
meaningless at best.
"""
from __future__ import annotations

from typing import Any

import httpx

from tool_orchestration.core.domain import ToolCallError

_JSONRPC_VERSION = "2.0"


class HTTPMCPClientAdapter:
    def __init__(self, server_aliases: dict[str, str] | None = None, client: httpx.AsyncClient | None = None) -> None:
        self._server_aliases = server_aliases or {}
        self._client = client or httpx.AsyncClient(timeout=30.0)

    def set_server_aliases(self, aliases: dict[str, str]) -> None:
        self._server_aliases = aliases

    def _resolve_endpoint(self, mcp_server_ref: str) -> str | None:
        if mcp_server_ref.startswith(("http://", "https://")):
            return mcp_server_ref
        return self._server_aliases.get(mcp_server_ref)

    async def call(
        self, *, mcp_server_ref: str, tool_name: str, arguments: dict[str, Any], tenant_id: str
    ) -> dict[str, Any]:
        endpoint = self._resolve_endpoint(mcp_server_ref)
        if endpoint is None:
            raise ToolCallError(tool_name, f"cannot resolve MCP server ref '{mcp_server_ref}' to an endpoint")

        request_id = f"{tool_name}-{tenant_id}"
        payload = {
            "jsonrpc": _JSONRPC_VERSION,
            "id": request_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        try:
            resp = await self._client.post(endpoint, json=payload, headers={"X-Tenant-Id": tenant_id})
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise ToolCallError(tool_name, str(e)) from e

        data = resp.json()
        if "error" in data:
            raise ToolCallError(tool_name, str(data["error"]))
        return data.get("result", {})
