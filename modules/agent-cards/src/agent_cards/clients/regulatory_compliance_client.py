"""HTTP adapter for Regulatory Compliance (Module 17) -- the compliance
half of the Trust Score Calculator's two real-peer signals. Reads that
module's own `GET /coverage` endpoint.

`HTTPRegulatoryComplianceClient` is a `ResilientHTTPClient` (retry +
circuit breaker on every outbound call — see resilience.py) carrying
this platform's service-to-service JWT (`ServiceBearerAuth`), since
Regulatory Compliance is a genuine platform peer.
"""
from __future__ import annotations

import httpx

from agent_cards.clients.resilience import ResilientHTTPClient
from agent_cards.security.jwt_auth import ServiceBearerAuth

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


class HTTPRegulatoryComplianceClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="regulatory-compliance", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="regulatory-compliance", auth=auth)

    async def coverage(self, *, tenant_id: str, framework_name: str) -> float | None:
        resp = await self._get(
            "/v1/regulatory-compliance/coverage", params={"tenant_id": tenant_id, "framework_name": framework_name},
        )
        return resp.json().get("coverage_percentage")
