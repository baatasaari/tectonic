"""HTTP adapters for this module's external dependencies: the source
connector runtime (a generic HTTP-based stand-in for Airbyte/PyAirbyte —
see the module README's "Design notes vs. the LLD") and the Secrets and
Credential Management module.

Every client below is a `ResilientHTTPClient` (retry + circuit breaker on
every outbound call — see resilience.py).
"""
from __future__ import annotations

from typing import Any

import httpx

from data_source_plugins.clients.resilience import ResilientHTTPClient
from data_source_plugins.core.ports import ExtractionResult
from data_source_plugins.security.jwt_auth import ServiceBearerAuth

_EXTRACT_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)
_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)

class HTTPSourceConnectorRuntime(ResilientHTTPClient):
    # Deliberately NOT wired with service-to-service JWT auth: this is a generic
    # HTTP-based stand-in for an external Airbyte/PyAirbyte-style connector runtime
    # (see the module README's "Design notes vs. the LLD"), not a platform peer
    # module — it has its own external auth model (e.g. per-connector credentials),
    # so `ServiceBearerAuth` (scoped to this platform's shared signing key) does not
    # apply here.
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, timeout=_EXTRACT_TIMEOUT, breaker_name="source-connector-runtime")

    async def extract(
        self, *, source_type: str, connection_config: dict[str, Any], credentials: dict[str, Any],
        query: dict[str, Any] | None = None,
    ) -> ExtractionResult:
        resp = await self._post(
            "/v1/extract",
            json={
                "source_type": source_type, "connection_config": connection_config,
                "credentials": credentials, "query": query,
            },
        )
        body = resp.json()
        return ExtractionResult(records=body.get("records", []), schema=body.get("schema", {}))


class HTTPSecretsClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="secrets-credential-management", shared_secret=shared_secret,
            ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="secrets", auth=auth)

    async def resolve(self, secrets_ref: str) -> dict[str, Any]:
        resp = await self._post("/v1/secrets/resolve", json={"secrets_ref": secrets_ref})
        return resp.json().get("credentials", {})
