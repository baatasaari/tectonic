"""The one generic HTTP adapter the Isolation Probe Service reuses
against every registered platform module -- no per-module code, because
every module already exposes `GET {list_path}?tenant_id=X` returning
`{"items": [...each with its own tenant_id...]}`. One instance is
constructed per configured `ProbeTargetConfig` (its own fixed
`base_url`/`list_path`/`audience`).

`HTTPTenantScopedListClient` is a `ResilientHTTPClient` (retry + circuit
breaker on every outbound call — see resilience.py) carrying this
platform's service-to-service JWT (`ServiceBearerAuth`), scoped to the
target's own `service_name` via `audience`.
"""
from __future__ import annotations

from typing import Any

import httpx

from multi_tenancy.clients.resilience import ResilientHTTPClient
from multi_tenancy.security.jwt_auth import ServiceBearerAuth

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)

# Every module's list endpoint is itself paginated; a probe takes a single, max-size
# page as its sample rather than walking every page -- a bounded, representative sample
# is what an isolation check needs, not a tenant's entire record set at that peer.
_SAMPLE_LIMIT = 200


class HTTPTenantScopedListClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, list_path: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", audience: str = "", ttl_seconds: int = 300,
        breaker_name: str = "",
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience=audience, shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(
            base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name=breaker_name or audience, auth=auth,
        )
        self._list_path = list_path

    async def list_tenant_scoped_items(self, *, tenant_id: str) -> list[dict[str, Any]]:
        resp = await self._get(self._list_path, params={"tenant_id": tenant_id, "limit": _SAMPLE_LIMIT})
        return resp.json().get("items", [])
