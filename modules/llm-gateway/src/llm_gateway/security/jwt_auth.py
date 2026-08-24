"""Service-to-service JWT bearer authentication (LLD gap fix: before this,
no module authenticated any of its inbound HTTP calls — any process that
could reach a module's port could call it, and every outbound call this
module makes to a peer carried no credential at all).

Shared-signing-key design, per the platform-wide decision this token
covers: every module holds the same HS256 secret (`TECTONIC_JWT_SHARED_SECRET`
— one Kubernetes Secret, referenced by every module's Helm chart under that
same env var name, not a per-module-prefixed one, since it genuinely is one
shared secret) and both mints and verifies tokens with it. This is
service-to-service auth for inter-module calls; it is not the platform's
external-facing user-auth story, which is a separate, larger concern (a
real API gateway/OAuth layer in front of the platform's own entry points)
out of scope for this fix.

- `mint_service_token` / `ServiceBearerAuth`: the outbound side. Every HTTP
  client this module owns attaches a short-lived (default 5 minute) token
  scoped to the specific peer being called via the `aud` (audience) claim —
  a token minted to call llm-gateway is rejected if replayed against
  tool-orchestration, limiting the blast radius of a leaked/intercepted
  token to the one peer it was meant for.
- `ServiceAuthMiddleware`: the inbound side. Verifies every request's
  `Authorization: Bearer <token>` against this module's own `service_name`
  as the required audience, except `/healthz` and `/metrics` (Kubernetes
  liveness/readiness probes and Prometheus scraping carry no auth token —
  requiring one there would break standard cluster tooling, not add
  security, since both are cluster-internal by convention already).
"""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from llm_gateway.telemetry.logging import get_logger

logger = get_logger(component="jwt_auth")

ALGORITHM = "HS256"
DEFAULT_TTL_SECONDS = 300
INSECURE_DEFAULT_SECRET = "dev-insecure-shared-secret-change-me"
_EXCLUDED_PATHS = frozenset({"/healthz", "/metrics"})


def mint_service_token(
    *, issuer: str, audience: str, shared_secret: str, ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Mints a short-lived token for THIS module (`issuer`) to call a
    specific peer (`audience`). A fresh token is minted per call (HMAC
    signing is cheap; there's no need to cache/reuse one across requests)."""
    now = int(time.time())
    payload = {"iss": issuer, "aud": audience, "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(payload, shared_secret, algorithm=ALGORITHM)


def verify_service_token(token: str, *, audience: str, shared_secret: str) -> dict[str, Any]:
    """Raises `jwt.PyJWTError` (or a subclass, e.g. `ExpiredSignatureError`,
    `InvalidAudienceError`) on any invalid token; returns the decoded claims
    on success."""
    return jwt.decode(token, shared_secret, algorithms=[ALGORITHM], audience=audience)


class ServiceBearerAuth(httpx.Auth):
    """An `httpx.Auth` flow: attaches a fresh `Authorization: Bearer <JWT>`
    header to every outbound request an `httpx.AsyncClient` makes, scoped
    to the specific peer (`audience`) that client talks to."""

    def __init__(
        self, *, issuer: str, audience: str, shared_secret: str, ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._shared_secret = shared_secret
        self._ttl_seconds = ttl_seconds

    def auth_flow(self, request: httpx.Request):
        token = mint_service_token(
            issuer=self._issuer, audience=self._audience,
            shared_secret=self._shared_secret, ttl_seconds=self._ttl_seconds,
        )
        request.headers["Authorization"] = f"Bearer {token}"
        yield request


class ServiceAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, audience: str, shared_secret: str) -> None:
        super().__init__(app)
        self._audience = audience
        self._shared_secret = shared_secret

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path in _EXCLUDED_PATHS:
            return await call_next(request)

        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return JSONResponse({"detail": "missing bearer token"}, status_code=401)

        try:
            verify_service_token(token, audience=self._audience, shared_secret=self._shared_secret)
        except jwt.ExpiredSignatureError:
            return JSONResponse({"detail": "token expired"}, status_code=401)
        except jwt.PyJWTError as exc:
            logger.warning("service_auth_rejected", path=request.url.path, error=str(exc))
            return JSONResponse({"detail": f"invalid token: {exc}"}, status_code=401)

        return await call_next(request)
