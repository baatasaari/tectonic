"""HTTP adapter for the Auditability dependency."""
from __future__ import annotations

from typing import Any

import httpx

from graph_db.security.jwt_auth import ServiceBearerAuth


class HTTPAuditabilityClient:
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="auditability", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=5.0, auth=auth)

    async def emit(self, event: dict[str, Any]) -> None:
        await self._client.post("/v1/auditability/events", json=event)
