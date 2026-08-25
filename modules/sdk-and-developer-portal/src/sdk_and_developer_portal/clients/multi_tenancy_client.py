"""HTTP adapter for Multi-tenancy (Module 30) -- the real tenant
registry `DeveloperAccountService` provisions every developer's
sandbox into. Calls that module's own real `POST
/v1/multi-tenancy/tenants` with `tier="sandbox"`.
"""
from __future__ import annotations

import httpx

from sdk_and_developer_portal.clients.resilience import ResilientHTTPClient
from sdk_and_developer_portal.security.jwt_auth import ServiceBearerAuth

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


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

    async def create_tenant(self, *, name: str, tier: str) -> str:
        resp = await self._post("/v1/multi-tenancy/tenants", json={"name": name, "tier": tier})
        return resp.json()["id"]
