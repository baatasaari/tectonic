"""HTTP adapter for FinOps (Module 26) -- the other of this module's two
real platform-peer dependencies. Reads that module's own `GET
/cost-reports/{tenant_id}`, the exact endpoint the Canary Health
Calculator's cost signal gates on.

`HTTPFinOpsClient` is a `ResilientHTTPClient` (retry + circuit breaker
on every outbound call — see resilience.py) carrying this platform's
service-to-service JWT (`ServiceBearerAuth`), since FinOps is a genuine
platform peer.
"""
from __future__ import annotations

import httpx

from deployment_strategy.clients.resilience import ResilientHTTPClient
from deployment_strategy.security.jwt_auth import ServiceBearerAuth

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


class HTTPFinOpsClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="finops", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="finops", auth=auth)

    async def cost_report_utilisation(self, *, tenant_id: str, period: str, budget_policy_id: str) -> float | None:
        # A budget_policy_id that doesn't exist (stale/mistyped) is a 404 from FinOps's
        # own GET /cost-reports/{tenant_id} -- "not configured", not an error this
        # module's callers should have to handle specially.
        resp = await self._get_optional(
            f"/v1/finops/cost-reports/{tenant_id}", params={"period": period, "budget_policy_id": budget_policy_id},
        )
        if resp is None:
            return None
        return resp.json().get("utilisation_ratio")
