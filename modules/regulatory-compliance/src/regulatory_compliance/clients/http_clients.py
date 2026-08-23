"""HTTP client adapters.

**Auditability.** Module 20 (Auditability) hasn't been built yet in this
platform, so `HTTPAuditabilityClient` targets a plausible-but-unverified
endpoint — the same documented-gap pattern used elsewhere (e.g. Sentinel
Agents' Tool Orchestration circuit-break call). Every call site wraps this
in try/except and treats a failure as "no enrichment available," never as
a reason to fail evidence-pack generation — this module's own recorded
`ControlImplementationEvent` rows remain the evidence source of record
either way.
"""
from __future__ import annotations

import httpx


class HTTPAuditabilityClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def query_control_events(self, tenant_id: str, control_name: str, date_range: dict | None = None) -> list[dict]:
        resp = await self._client.get(
            "/v1/auditability/events",
            params={"tenant_id": tenant_id, "control_name": control_name},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("events", []) if isinstance(data, dict) else list(data)
