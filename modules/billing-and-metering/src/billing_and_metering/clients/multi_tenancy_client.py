"""HTTP adapter for Multi-tenancy (Module 30) -- pushes a tenant's
pricing-plan module list to Multi-tenancy's own feature-flag store
(`POST /v1/multi-tenancy/tenants/{id}/entitlements`) whenever
`PricingPlanService.create` gives that tenant a plan of its own, and
reads it back (`GET /tenants/{id}/gate?module=...`) so
`MeteringService` never meters -- and therefore never bills -- a
resource for a module the tenant isn't currently entitled to.

Both calls are deliberately best-effort/fail-open: a plan is a real,
committed billing record the moment it's created, and a gate check
that can't be answered must never block metering, the same posture
`EntitlementGateMiddleware` already takes platform-wide. `
sync_entitlements` and `gate` both swallow their own errors (log a
warning, return a safe default) rather than raising -- callers never
need a try/except around either.
"""
from __future__ import annotations

import httpx

from billing_and_metering.clients.resilience import ResilientHTTPClient
from billing_and_metering.security.jwt_auth import ServiceBearerAuth
from billing_and_metering.telemetry.logging import get_logger

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)

logger = get_logger(component="multi_tenancy_client")


class HTTPMultiTenancyClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="multi-tenancy", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(
            base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="multi-tenancy", fail_max=5, auth=auth,
        )

    async def sync_entitlements(self, *, tenant_id: str, module_names: list[str]) -> None:
        try:
            await self._post(
                f"/v1/multi-tenancy/tenants/{tenant_id}/entitlements", json={"module_names": module_names},
            )
        except Exception:
            logger.warning(
                "entitlement_sync_failed", tenant_id=tenant_id, module_names=module_names,
                hint="multi-tenancy unreachable or rejected the sync; the pricing plan was still created",
            )

    async def gate(self, *, tenant_id: str, module: str) -> tuple[bool, str]:
        try:
            resp = await self._get(f"/v1/multi-tenancy/tenants/{tenant_id}/gate", params={"module": module})
            body = resp.json()
            return bool(body["allowed"]), str(body.get("reason", ""))
        except Exception as exc:
            logger.warning(
                "entitlement_gate_unreachable", tenant_id=tenant_id, module=module, error=str(exc),
                hint="failing open -- metering proceeds as if entitled, the same posture "
                "EntitlementGateMiddleware takes platform-wide",
            )
            return True, ""
