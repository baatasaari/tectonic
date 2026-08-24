"""HTTP adapter for the Auditability dependency.

`HTTPAuditabilityClient` is a `ResilientHTTPClient` (retry + circuit
breaker on every outbound call — see resilience.py). `emit()` stays
best-effort as before this wiring existed: audit-event delivery must
never be the reason a graph write fails.
"""
from __future__ import annotations

from typing import Any

import httpx

from graph_db.clients.resilience import CircuitBreakerError, ResilientHTTPClient
from graph_db.security.jwt_auth import ServiceBearerAuth
from graph_db.telemetry.logging import get_logger

logger = get_logger(component="http_clients")

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=5.0)


class HTTPAuditabilityClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="auditability", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="auditability", fail_max=10, auth=auth)

    async def emit(self, event: dict[str, Any]) -> None:
        try:
            await self._post("/v1/auditability/events", json=event)
        except (httpx.HTTPError, CircuitBreakerError) as exc:
            logger.warning("auditability_emit_failed", error=str(exc))
