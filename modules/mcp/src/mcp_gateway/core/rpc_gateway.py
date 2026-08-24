"""RPC Gateway (LLD §2 sub-components, §Level 3 "Sequence: a governed
tools/call"): the one place an inbound JSON-RPC request actually gets
enforced against the Access Policy Engine and forwarded to a registered
server's real backend.
"""
from __future__ import annotations

from mcp_gateway.core.access_policy_engine import AccessPolicyEngine
from mcp_gateway.core.domain import (
    AccessDeniedError,
    JsonRpcRequest,
    JsonRpcResponse,
    McpServerNotFoundError,
)
from mcp_gateway.core.ports import MCPBackendClient, MCPGatewayRepository

# JSON-RPC 2.0 reserves -32000 to -32099 for implementation-defined server
# errors; -32001 is this gateway's own "not authorized" code, distinct from
# any error code the backend itself might return.
_ACCESS_DENIED_CODE = -32001


class RpcGateway:
    def __init__(self, repository: MCPGatewayRepository, backend: MCPBackendClient) -> None:
        self._repository = repository
        self._backend = backend

    async def handle(self, *, server_id: str, tenant_id: str, request: JsonRpcRequest) -> JsonRpcResponse:
        server = await self._repository.get_server(server_id)
        if server is None:
            raise McpServerNotFoundError(server_id)

        tool_name = None
        if request.method == "tools/call" and request.params:
            tool_name = request.params.get("name")

        try:
            await AccessPolicyEngine(self._repository).authorize(
                server_id=server_id, tenant_id=tenant_id, method=request.method, tool_name=tool_name,
            )
        except AccessDeniedError as exc:
            return JsonRpcResponse(
                jsonrpc="2.0", id=request.id, error={"code": _ACCESS_DENIED_CODE, "message": exc.reason},
            )

        return await self._backend.send(server.base_url, request)
