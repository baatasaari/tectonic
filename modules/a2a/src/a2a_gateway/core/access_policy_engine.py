"""Access Policy Engine (LLD §2 sub-components): deny-by-default. An
external caller with no policy row for a tenant has zero access; where a
policy does exist, the requested skill is checked against its
`allowed_skills` allow-list (`null` = every skill this platform
publishes) -- the same shape as MCP's own engine (Module 21), applied
here to "per-skill, not just per-caller."
"""
from __future__ import annotations

from a2a_gateway.core.domain import AccessDeniedError
from a2a_gateway.core.ports import A2AGatewayRepository


class AccessPolicyEngine:
    def __init__(self, repository: A2AGatewayRepository) -> None:
        self._repository = repository

    async def authorize(self, *, caller_agent_id: str, tenant_id: str, skill_id: str) -> None:
        """Raises AccessDeniedError; returns normally if allowed."""
        policy = await self._repository.get_access_policy(caller_agent_id, tenant_id)
        if policy is None:
            raise AccessDeniedError(f"caller '{caller_agent_id}' has no access policy for tenant '{tenant_id}'")

        if policy.allowed_skills is None:
            return  # null allow-list = every skill this platform publishes is permitted

        if skill_id not in policy.allowed_skills:
            raise AccessDeniedError(f"caller '{caller_agent_id}' is not authorized to invoke skill '{skill_id}'")
