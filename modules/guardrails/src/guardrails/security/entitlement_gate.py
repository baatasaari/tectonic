"""Entitlement gate middleware -- the platform's reference implementation
of the per-module feature-flag check every selectable module is meant to
adopt (see the rollout playbook doc for the mechanical steps to apply
this same pattern elsewhere).

Layered *after* `ServiceAuthMiddleware` in the middleware stack:
authenticate first (who is calling), entitle second (does the calling
tenant's subscription include this module). In `main.py`, that ordering
means `EntitlementGateMiddleware` is added to the app BEFORE
`ServiceAuthMiddleware` -- Starlette's `add_middleware` makes the
most-recently-added middleware the outermost layer, so the middleware
added last runs first.

Calls Multi-tenancy's real `GET /tenants/{tenant_id}/gate?module=<this
module's own service_name>` -- the same endpoint `TenantRegistryService.
gate()` backs (see Multi-tenancy's own `core/tenant_registry_service.py`
docstring for the full allow/deny semantics, including why a tenant that
has never had entitlements configured is allowed through). Reads
`X-Tenant-Id` directly off the request rather than through FastAPI's DI,
since middleware runs before dependency resolution; a request with no
tenant header has nothing to gate on and passes through unchanged, the
same posture this module's own `resolve_tenant_id` dependency takes
elsewhere.

Fails OPEN. This is the one deliberate, load-bearing contrast with
`ServiceAuthMiddleware`'s zero-trust fail-closed posture: authentication
protects a security boundary, where "let it through" on doubt is
unacceptable. Entitlement is a commercial/billing concern layered on top
of an already-authenticated request -- Multi-tenancy being unreachable
must never cascade into every module's request path failing platform-
wide. On any error (timeout, non-2xx, the breaker open) this middleware
logs a loud warning and allows the request through.

A short in-process TTL cache plus a circuit breaker bound the added load
on Multi-tenancy and the added latency on this module's own request
path during a real Multi-tenancy outage: at most one live call per
tenant per `cache_ttl_seconds`, and once `fail_max` consecutive calls
fail the breaker opens and every call fails open immediately (no network
round trip) until its timeout elapses.
"""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from datetime import timedelta

import httpx
from aiobreaker import CircuitBreaker
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from guardrails.security.jwt_auth import ServiceBearerAuth
from guardrails.telemetry.logging import get_logger

logger = get_logger(component="entitlement_gate")

_EXCLUDED_PATHS = frozenset({"/healthz", "/metrics"})
_DEFAULT_TIMEOUT = httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0)


class EntitlementGateMiddleware(BaseHTTPMiddleware):
    def __init__(
        self, app: ASGIApp, *, module_name: str, multi_tenancy_base_url: str,
        issuer: str = "", shared_secret: str = "", cache_ttl_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(app)
        self._module_name = module_name
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, tuple[float, bool, str]] = {}
        auth = ServiceBearerAuth(
            issuer=issuer, audience="multi-tenancy", shared_secret=shared_secret,
        ) if issuer else None
        self._client = client or httpx.AsyncClient(
            base_url=multi_tenancy_base_url, timeout=_DEFAULT_TIMEOUT, auth=auth,
        )
        self._breaker = CircuitBreaker(
            fail_max=5, timeout_duration=timedelta(seconds=30), name="multi-tenancy-entitlement-gate",
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path in _EXCLUDED_PATHS:
            return await call_next(request)

        tenant_id = request.headers.get("x-tenant-id")
        if not tenant_id:
            return await call_next(request)

        allowed, reason = await self._check(tenant_id)
        if not allowed:
            return JSONResponse({"detail": reason}, status_code=402)

        return await call_next(request)

    async def _check(self, tenant_id: str) -> tuple[bool, str]:
        cached = self._cache.get(tenant_id)
        now = time.monotonic()
        if cached is not None and now - cached[0] < self._cache_ttl_seconds:
            return cached[1], cached[2]

        try:
            resp = await self._breaker.call_async(self._do_request, tenant_id)
            body = resp.json()
            allowed, reason = bool(body["allowed"]), str(body.get("reason", ""))
        except Exception as exc:
            logger.warning(
                "entitlement_gate_unreachable", tenant_id=tenant_id, module=self._module_name, error=str(exc),
            )
            allowed, reason = True, ""

        self._cache[tenant_id] = (now, allowed, reason)
        return allowed, reason

    async def _do_request(self, tenant_id: str) -> httpx.Response:
        # raise_for_status() must run inside the breaker-tracked call so a 5xx counts
        # as a breaker failure -- the same reasoning clients/resilience.py documents.
        resp = await self._client.get(
            f"/v1/multi-tenancy/tenants/{tenant_id}/gate", params={"module": self._module_name},
        )
        resp.raise_for_status()
        return resp
