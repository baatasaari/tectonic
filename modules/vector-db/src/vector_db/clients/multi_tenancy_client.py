"""HTTP adapter for the Multi-tenancy quota pre-flight dependency
(Module 30), mirroring `http_clients.py`'s `HTTPEmbeddingProvider` and
Billing and Metering's / LLM Gateway's own `HTTPMultiTenancyClient`.

`HTTPMultiTenancyClient` is a `ResilientHTTPClient` (retry + circuit
breaker on every outbound call), and fails open on any error --
unreachable, timed out, or a non-2xx response -- the same posture
`EntitlementGateMiddleware` already takes platform-wide: a Multi-tenancy
outage must never itself block every write this module makes.
"""
from __future__ import annotations

import httpx

from vector_db.clients.resilience import ResilientHTTPClient
from vector_db.security.jwt_auth import ServiceBearerAuth
from vector_db.telemetry.logging import get_logger

logger = get_logger(component="multi_tenancy_client")

_SHORT_TIMEOUT = httpx.Timeout(connect=2.0, read=3.0, write=2.0, pool=2.0)


class HTTPMultiTenancyClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="multi-tenancy", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="multi-tenancy", auth=auth)

    async def check_quota(
        self, *, tenant_id: str, resource_class: str, amount: float = 1.0, current_usage: float | None = None,
    ) -> tuple[bool, str]:
        try:
            resp = await self._post(
                f"/v1/multi-tenancy/tenants/{tenant_id}/quota/check",
                json={"resource_class": resource_class, "amount": amount, "current_usage": current_usage},
            )
            body = resp.json()
            return bool(body["allowed"]), str(body.get("reason", ""))
        except Exception as exc:
            logger.warning(
                "quota_check_unreachable", tenant_id=tenant_id, resource_class=resource_class, error=str(exc),
            )
            return True, ""
