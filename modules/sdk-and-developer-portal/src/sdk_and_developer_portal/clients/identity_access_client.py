"""HTTP adapter for Identity and Access (Module 31) -- the real
identity registry `DeveloperAccountService` provisions every developer
into. Calls that module's own real `POST /v1/identity-access/identities`,
`POST /v1/identity-access/identities/{id}/revoke`, and
`POST /v1/identity-access/tokens`.
"""
from __future__ import annotations

from typing import Any

import httpx

from sdk_and_developer_portal.clients.resilience import ResilientHTTPClient
from sdk_and_developer_portal.security.jwt_auth import ServiceBearerAuth

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

    async def register_identity(self, *, name: str, type_: str, role_names: list[str]) -> str:
        resp = await self._post(
            "/v1/identity-access/identities", json={"name": name, "type": type_, "role_names": role_names},
        )
        return resp.json()["id"]

    async def revoke_identity(self, identity_id: str) -> None:
        await self._post(f"/v1/identity-access/identities/{identity_id}/revoke")

    async def issue_token(self, *, identity_id: str, requested_scopes: list[str] | None) -> dict[str, Any]:
        resp = await self._post(
            "/v1/identity-access/tokens",
            json={"identity_id": identity_id, "requested_scopes": requested_scopes},
        )
        return resp.json()
