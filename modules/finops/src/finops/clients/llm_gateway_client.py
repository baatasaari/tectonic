"""HTTP adapter for LLM Gateway (Module 3) -- this module's one real
platform-peer dependency, and its source of truth for LLM spend. Reads
that module's own `GET /admin/virtual-keys` and `GET
/admin/budgets/{id}`, the exact `current_spend` LLM Gateway's own
`CostGovernanceEngine` already settles after every completion.

`HTTPLLMGatewayClient` is a `ResilientHTTPClient` (retry + circuit
breaker on every outbound call — see resilience.py) carrying this
platform's service-to-service JWT (`ServiceBearerAuth`), since LLM
Gateway is a genuine platform peer.
"""
from __future__ import annotations

import httpx

from finops.clients.resilience import ResilientHTTPClient
from finops.security.jwt_auth import ServiceBearerAuth

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
_VIRTUAL_KEY_PAGE_LIMIT = 200


class HTTPLLMGatewayClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="llm-gateway", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="llm-gateway", auth=auth)

    async def tenant_spend(self, tenant_id: str) -> float:
        resp = await self._get(
            "/v1/llm-gateway/admin/virtual-keys", params={"tenant_id": tenant_id, "limit": _VIRTUAL_KEY_PAGE_LIMIT},
        )
        virtual_keys = resp.json().get("items", [])

        # Multiple virtual keys can share one budget_policy_ref (e.g. one per provider
        # scope for the same tenant budget) -- dedupe so that budget's current_spend
        # isn't summed into the total once per key referencing it.
        budget_policy_refs = {vk["budget_policy_ref"] for vk in virtual_keys}

        total = 0.0
        for budget_policy_ref in budget_policy_refs:
            status_resp = await self._get(f"/v1/llm-gateway/admin/budgets/{budget_policy_ref}")
            total += status_resp.json()["current_spend"]
        return total
