"""HTTP adapter that fetches a real, live OpenAPI spec from any
configured peer module's own `GET /openapi.json` -- the exact spec a
developer's browser would see at that module's own `/docs`.

Unlike this module's other clients, `HTTPModuleSpecClient` isn't
scoped to one fixed `base_url`: `ModuleCatalogService` fans out across
every configured `CatalogTargetConfig`, each with its own base_url and
its own audience. Retry-on-5xx (`_with_retry`, from `resilience.py`)
is reused directly; no circuit breaker here -- each target is called
at most once per sync, not the hot, repeated-call pattern breakers are
meant to protect.

`/openapi.json` sits behind every peer's own `ServiceAuthMiddleware`
just like any other route (only `/healthz`/`/metrics` are excluded),
so this client mints a real scoped token per target -- even fetching
documentation respects the platform's real security model.
"""
from __future__ import annotations

from typing import Any

import httpx

from sdk_and_developer_portal.clients.resilience import DEFAULT_TIMEOUT, _with_retry
from sdk_and_developer_portal.security.jwt_auth import mint_service_token


class HTTPModuleSpecClient:
    def __init__(
        self, *, issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._issuer = issuer
        self._shared_secret = shared_secret
        self._ttl_seconds = ttl_seconds
        self._client = client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)

    @_with_retry()
    async def fetch_spec(self, *, base_url: str, audience: str) -> dict[str, Any]:
        headers = {}
        if self._issuer:
            token = mint_service_token(
                issuer=self._issuer, audience=audience, shared_secret=self._shared_secret,
                ttl_seconds=self._ttl_seconds,
            )
            headers["Authorization"] = f"Bearer {token}"

        resp = await self._client.get(f"{base_url}/openapi.json", headers=headers)
        resp.raise_for_status()
        return resp.json()
