"""Access Policy Engine (LLD §2 sub-components): deny-by-default. A
tenant with no policy row for a server has zero access; where a policy
does exist, `tools/call` is checked against its `allowed_tools`
allow-list specifically (every other method only needs the server-level
policy row to exist) -- see the module README's "Design notes vs. the
LLD" for why `tools/call` alone gets this extra check.
"""
from __future__ import annotations

from mcp_gateway.core.domain import AccessDeniedError
from mcp_gateway.core.ports import MCPGatewayRepository

_TOOL_SCOPED_METHOD = "tools/call"


class AccessPolicyEngine:
    def __init__(self, repository: MCPGatewayRepository) -> None:
        self._repository = repository

    async def authorize(self, *, server_id: str, tenant_id: str, method: str, tool_name: str | None) -> None:
        """Raises AccessDeniedError; returns normally if allowed."""
        policy = await self._repository.get_access_policy(server_id, tenant_id)
        if policy is None:
            raise AccessDeniedError(f"tenant '{tenant_id}' has no access policy for server '{server_id}'")

        if method != _TOOL_SCOPED_METHOD:
            return

        if policy.allowed_tools is None:
            return  # null allow-list = every tool on this server is permitted

        if tool_name is None:
            raise AccessDeniedError("tools/call request did not name a tool")

        if tool_name not in policy.allowed_tools:
            raise AccessDeniedError(f"tenant '{tenant_id}' is not authorized to call tool '{tool_name}'")
