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

Bounded-staleness cache, deny-by-default outside it (independent
architecture assessment's own P0 Phase 1A closure item -- this replaced
an earlier version of this file that failed open, unconditionally and
forever, on ANY Multi-tenancy outage; that older posture meant a
prolonged outage silently and permanently disabled entitlement
enforcement platform-wide for as long as the outage lasted, which the
assessment correctly flagged as not actually "done"). The new posture:

- A decision this middleware itself verified via a real, successful call
  to Multi-tenancy is cached as VERIFIED, timestamped with the monotonic
  clock reading at verification time.
- Within `cache_ttl_seconds` of that verification, the cached decision is
  served with no network call at all (unchanged from before -- this is
  the existing "at most one live call per tenant per cache_ttl_seconds"
  behaviour, still the common case).
- Once the cache entry is older than `cache_ttl_seconds`, a fresh call is
  attempted. If it succeeds, the cache is refreshed and the new decision
  served. If it fails (timeout, non-2xx, the breaker open) -- this is the
  bounded-staleness fallback: the last VERIFIED decision is still served,
  but only while it is younger than `max_staleness_seconds`. This is
  fail-open in the sense that a real Multi-tenancy outage does not take
  every gated module down with it, but it is bounded: it is serving a
  real decision this middleware itself confirmed at some point in the
  recent past, not blindly assuming "allowed" the way the old version
  did, and it stops the instant that decision is older than
  `max_staleness_seconds`.
- Once no VERIFIED decision exists within `max_staleness_seconds` (a cold
  cache with Multi-tenancy already unreachable, or an outage that has
  outlasted the staleness bound) the request is DENIED -- fail closed,
  the opposite of this file's old default. This is the one deliberate
  behavour change from the "entitlement never fails closed" posture
  documented here previously: an entitlement decision this middleware
  has never been able to verify, or can no longer trust as recent, must
  not be silently treated as "allowed".

Every cached decision is HMAC-signed with the same shared secret this
module already uses for service-to-service JWTs (`jwt_auth.py`), binding
tenant_id + allowed + reason + verified_at together. This cache is an
in-process dict today, so signing does not defend against a same-process
attacker -- it defends against silent corruption/type confusion (a bad
merge of this cache into a future shared/out-of-process store, e.g.
Redis, per this module's own established pattern of moving in-process
state to Redis for session state) being served as a trusted decision
without anyone noticing: a signature mismatch is treated exactly like a
missing entry, never like a verified one.

Both the stale-serve path and the fail-closed path emit a dedicated
Prometheus metric (telemetry/metrics.py) so an operator can see and
alert on a live Multi-tenancy outage's real blast radius, instead of it
being invisible the way silent fail-open was.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

import httpx
from aiobreaker import CircuitBreaker
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from conversational_engine.security.jwt_auth import ServiceBearerAuth
from conversational_engine.telemetry.logging import get_logger
from conversational_engine.telemetry.metrics import (
    entitlement_gate_fail_closed_total,
    entitlement_gate_stale_served_total,
)

logger = get_logger(component="entitlement_gate")

_EXCLUDED_PATHS = frozenset({"/healthz", "/metrics"})
_DEFAULT_TIMEOUT = httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0)
# Bounded-staleness window: how long a VERIFIED decision may still be served
# after Multi-tenancy becomes unreachable, before this middleware switches to
# fail-closed. Deliberately a small multiple of the default cache_ttl_seconds
# (30s) rather than e.g. hours -- long enough to ride out a rolling restart
# or a brief network blip, short enough that a real, sustained outage denies
# rather than silently disabling entitlement enforcement platform-wide.
_DEFAULT_MAX_STALENESS_SECONDS = 300.0


@dataclass(frozen=True)
class _CachedDecision:
    allowed: bool
    reason: str
    verified_at: float  # time.monotonic() reading when this was last confirmed via a real call
    signature: str


class EntitlementGateMiddleware(BaseHTTPMiddleware):
    def __init__(
        self, app: ASGIApp, *, module_name: str, multi_tenancy_base_url: str,
        issuer: str = "", shared_secret: str = "", cache_ttl_seconds: float = 30.0,
        max_staleness_seconds: float = _DEFAULT_MAX_STALENESS_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(app)
        self._module_name = module_name
        self._cache_ttl_seconds = cache_ttl_seconds
        self._max_staleness_seconds = max_staleness_seconds
        self._sign_key = (shared_secret or "").encode()
        self._cache: dict[str, _CachedDecision] = {}
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

    def _sign(self, tenant_id: str, allowed: bool, reason: str, verified_at: float) -> str:
        message = f"{tenant_id}|{allowed}|{reason}|{verified_at}".encode()
        return hmac.new(self._sign_key, message, hashlib.sha256).hexdigest()

    def _verified_cache_entry(self, tenant_id: str) -> _CachedDecision | None:
        """Returns the cached decision only if its signature still matches --
        a mismatch (corruption, or a future out-of-process store this cache
        moves to being written by something else) is treated identically to
        no cached decision at all, never as a trustworthy one."""
        cached = self._cache.get(tenant_id)
        if cached is None:
            return None
        expected = self._sign(tenant_id, cached.allowed, cached.reason, cached.verified_at)
        if not hmac.compare_digest(expected, cached.signature):
            logger.warning("entitlement_gate_cache_signature_mismatch", tenant_id=tenant_id)
            return None
        return cached

    async def _check(self, tenant_id: str) -> tuple[bool, str]:
        now = time.monotonic()
        cached = self._verified_cache_entry(tenant_id)
        if cached is not None and now - cached.verified_at < self._cache_ttl_seconds:
            return cached.allowed, cached.reason

        try:
            resp = await self._breaker.call_async(self._do_request, tenant_id)
            body = resp.json()
            allowed, reason = bool(body["allowed"]), str(body.get("reason", ""))
        except Exception as exc:
            return self._fallback(tenant_id, cached, now, exc)

        signature = self._sign(tenant_id, allowed, reason, now)
        self._cache[tenant_id] = _CachedDecision(
            allowed=allowed, reason=reason, verified_at=now, signature=signature,
        )
        return allowed, reason

    def _fallback(
        self, tenant_id: str, cached: _CachedDecision | None, now: float, exc: Exception,
    ) -> tuple[bool, str]:
        """Multi-tenancy is unreachable (or the breaker is open). Serve the
        last VERIFIED decision if one exists and is still within the bounded
        staleness window; otherwise fail closed. Never silently allow."""
        age = None if cached is None else now - cached.verified_at
        if cached is not None and age is not None and age < self._max_staleness_seconds:
            logger.warning(
                "entitlement_gate_serving_stale_decision", tenant_id=tenant_id, module=self._module_name,
                age_seconds=round(age, 1), error=str(exc),
            )
            entitlement_gate_stale_served_total.labels(module=self._module_name).inc()
            return cached.allowed, cached.reason

        logger.warning(
            "entitlement_gate_fail_closed", tenant_id=tenant_id, module=self._module_name,
            cached_age_seconds=None if age is None else round(age, 1), error=str(exc),
        )
        entitlement_gate_fail_closed_total.labels(module=self._module_name).inc()
        return False, "entitlement service unavailable and no recent verified decision cached"

    async def _do_request(self, tenant_id: str) -> httpx.Response:
        # raise_for_status() must run inside the breaker-tracked call so a 5xx counts
        # as a breaker failure -- the same reasoning clients/resilience.py documents.
        resp = await self._client.get(
            f"/v1/multi-tenancy/tenants/{tenant_id}/gate", params={"module": self._module_name},
        )
        resp.raise_for_status()
        return resp
