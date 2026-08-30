"""HTTP adapter for Auditability (Module 20) -- the real per-module
usage-count source `MeteringService` reads every non-`"llm.cost_usd"`
resource from. Calls that module's own real `GET
/v1/auditability/events` scoped by `source_module` and the period
window, and returns the `total` it already reports -- `limit=1` is
enough, this client never pages through and counts events itself.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from billing_and_metering.clients.resilience import ResilientHTTPClient
from billing_and_metering.security.jwt_auth import ServiceBearerAuth

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

    async def count_events(
        self, *, tenant_id: str, source_module: str, occurred_after: Any = None, occurred_before: Any = None,
    ) -> int:
        params: dict[str, Any] = {"tenant_id": tenant_id, "source_module": source_module, "limit": 1}
        if occurred_after is not None:
            params["occurred_after"] = _isoformat(occurred_after)
        if occurred_before is not None:
            params["occurred_before"] = _isoformat(occurred_before)

        resp = await self._get("/v1/auditability/events", params=params)
        return int(resp.json()["total"])


def _isoformat(value: Any) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)
