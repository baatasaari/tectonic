"""HTTP adapter for FinOps (Module 26) -- the real dollar-cost source
`MeteringService` reads `"llm.cost_usd"` from. Calls that module's own
real `GET /v1/finops/cost-reports/{tenant_id}` and returns
`total_cost` -- the same figure FinOps's own budget alerts are computed
from, never a second cost-computation pipeline.
"""
from __future__ import annotations

import httpx

from billing_and_metering.clients.resilience import ResilientHTTPClient
from billing_and_metering.security.jwt_auth import ServiceBearerAuth

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


class HTTPFinOpsClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="finops", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(
            base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="finops", fail_max=5, auth=auth,
        )

    async def get_total_cost(self, *, tenant_id: str, period: str) -> float:
        resp = await self._get(f"/v1/finops/cost-reports/{tenant_id}", params={"period": period})
        return float(resp.json()["total_cost"])
