"""HTTP adapter for Auditability (Module 20) -- the real event history
`AdoptionMetricsService` reads a developer sandbox's activity from.
Calls that module's own real `GET /v1/auditability/events`, reading
only `total` (a `limit=1, offset=0` call) or one targeted event at a
specific `offset` -- never a full-history scan.
"""
from __future__ import annotations

from datetime import datetime

import httpx

from sdk_and_developer_portal.clients.resilience import ResilientHTTPClient
from sdk_and_developer_portal.security.jwt_auth import ServiceBearerAuth

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


class HTTPAuditabilityClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="auditability", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(
            base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="auditability", fail_max=5, auth=auth,
        )

    async def count_events(self, *, tenant_id: str) -> int:
        resp = await self._get("/v1/auditability/events", params={"tenant_id": tenant_id, "limit": 1, "offset": 0})
        return int(resp.json()["total"])

    async def get_event_occurred_at(self, *, tenant_id: str, offset: int) -> datetime:
        resp = await self._get(
            "/v1/auditability/events", params={"tenant_id": tenant_id, "limit": 1, "offset": offset},
        )
        items = resp.json()["items"]
        return datetime.fromisoformat(items[0]["occurred_at"])
