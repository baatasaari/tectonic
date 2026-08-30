"""HTTP adapter for Multi-tenancy's real `POST /tenants/{id}/quota/check`
(independent architecture assessment §5.2 / §3.4 point 5) -- the same
reference shape Billing and Metering's own `HTTPMultiTenancyClient.gate`
already established for the entitlement gate check.

Fails OPEN: a quota check that can't be answered (Multi-tenancy
unreachable, timing out, the breaker open) must never block every
completion request platform-wide -- the same posture
`EntitlementGateMiddleware` already takes for entitlement, and Billing
and Metering's own `HTTPMultiTenancyClient.gate` already takes for the
metering-time entitlement check. Errors are swallowed (logged, a safe
default returned) rather than raised -- `LLMGatewayService.complete`
never needs a try/except around this call.
"""
from __future__ import annotations

import httpx

from llm_gateway.clients.resilience import ResilientHTTPClient
from llm_gateway.security.jwt_auth import ServiceBearerAuth
from llm_gateway.telemetry.logging import get_logger

_SHORT_TIMEOUT = httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0)

logger = get_logger(component="multi_tenancy_client")


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
        self, *, tenant_id: str, resource_class: str, amount: float = 1.0,
    ) -> tuple[bool, str]:
        try:
            resp = await self._post(
                f"/v1/multi-tenancy/tenants/{tenant_id}/quota/check",
                json={"resource_class": resource_class, "amount": amount},
            )
            body = resp.json()
            return bool(body["allowed"]), str(body.get("reason", ""))
        except Exception as exc:
            logger.warning(
                "quota_check_unreachable", tenant_id=tenant_id, resource_class=resource_class, error=str(exc),
                hint="failing open -- the request proceeds as if within quota, the same posture "
                "EntitlementGateMiddleware takes platform-wide",
            )
            return True, ""
