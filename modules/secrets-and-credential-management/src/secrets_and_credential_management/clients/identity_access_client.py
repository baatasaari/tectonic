"""HTTP adapter for Identity and Access (Module 31) -- the real
zero-trust gate `SecretAccessService.retrieve` calls on every retrieval.
Posts to that module's own real `POST /v1/identity-access/authorize`
with a scope of the shape `secret:{tenant_id}:{namespace}:read`.

`HTTPIdentityAccessClient` is a `ResilientHTTPClient` (retry + circuit
breaker -- see resilience.py) carrying this platform's service-to-service
JWT (`ServiceBearerAuth`), since Identity and Access is a genuine
platform peer, not a stand-in.
"""
from __future__ import annotations

from typing import Any

import httpx

from secrets_and_credential_management.clients.resilience import ResilientHTTPClient
from secrets_and_credential_management.security.jwt_auth import ServiceBearerAuth

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


class HTTPIdentityAccessClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="identity-and-access", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(
            base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="identity-and-access",
            fail_max=5, auth=auth,
        )

    async def authorize(self, *, token: str, required_scope: str) -> dict[str, Any]:
        resp = await self._post(
            "/v1/identity-access/authorize", json={"token": token, "required_scope": required_scope},
        )
        return resp.json()
