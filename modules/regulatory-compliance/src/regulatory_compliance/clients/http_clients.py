"""HTTP client adapters.

**Auditability.** Module 20 (Auditability) hasn't been built yet in this
platform, so `HTTPAuditabilityClient` targets a plausible-but-unverified
endpoint — the same documented-gap pattern used elsewhere (e.g. Sentinel
Agents' Tool Orchestration circuit-break call). Every call site wraps this
in try/except and treats a failure as "no enrichment available," never as
a reason to fail evidence-pack generation — this module's own recorded
`ControlImplementationEvent` rows remain the evidence source of record
either way.

`HTTPAuditabilityClient` is a `ResilientHTTPClient` (retry + circuit
breaker on every outbound call — see resilience.py).
"""
from __future__ import annotations

import httpx

class HTTPAuditabilityClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="auditability", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="auditability", fail_max=10, auth=auth)

    async def query_control_events(self, tenant_id: str, control_name: str, date_range: dict | None = None) -> list[dict]:
        resp = await self._get(
            "/v1/auditability/events",
            params={"tenant_id": tenant_id, "control_name": control_name},
        )
        data = resp.json()
        return data.get("events", []) if isinstance(data, dict) else list(data)
