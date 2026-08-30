"""HTTP adapter for Auditability (Module 20) -- this module's one real
platform-peer dependency. Posts to that module's own real `POST
/v1/auditability/events`, the identical real-peer emission pattern this
platform's earlier modules (Human Oversight, Sentinel Agents,
Regulatory Compliance) already established.

`HTTPAuditabilityClient` is a `ResilientHTTPClient` (retry + circuit
breaker on every outbound call — see resilience.py) carrying this
platform's service-to-service JWT (`ServiceBearerAuth`), since
Auditability is a genuine platform peer. `source_module` is never sent
in the body -- Auditability derives it from the verified inbound JWT's
`iss` claim itself (see that module's own `security/jwt_auth.py`).
"""
from __future__ import annotations

from typing import Any

import httpx

from identity_and_access.clients.resilience import ResilientHTTPClient
from identity_and_access.security.jwt_auth import ServiceBearerAuth

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
            base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="auditability", fail_max=10, auth=auth,
        )

    async def emit(self, event: dict[str, Any]) -> None:
        await self._post("/v1/auditability/events", json=event)
