"""HTTP adapters for this module's external dependencies: the source
connector runtime (a generic HTTP-based stand-in for Airbyte/PyAirbyte —
see the module README's "Design notes vs. the LLD") and the Secrets and
Credential Management module.
"""
from __future__ import annotations

from typing import Any

import httpx

from data_source_plugins.core.ports import ExtractionResult
from data_source_plugins.security.jwt_auth import ServiceBearerAuth


class HTTPSourceConnectorRuntime:
    # Deliberately NOT wired with service-to-service JWT auth: this is a generic
    # HTTP-based stand-in for an external Airbyte/PyAirbyte-style connector runtime
    # (see the module README's "Design notes vs. the LLD"), not a platform peer
    # module — it has its own external auth model (e.g. per-connector credentials),
    # so `ServiceBearerAuth` (scoped to this platform's shared signing key) does not
    # apply here.
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=60.0)

    async def extract(
        self, *, source_type: str, connection_config: dict[str, Any], credentials: dict[str, Any],
        query: dict[str, Any] | None = None,
    ) -> ExtractionResult:
        resp = await self._client.post(
            "/v1/extract",
            json={
                "source_type": source_type, "connection_config": connection_config,
                "credentials": credentials, "query": query,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        return ExtractionResult(records=body.get("records", []), schema=body.get("schema", {}))


class HTTPSecretsClient:
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="secrets-credential-management", shared_secret=shared_secret,
            ttl_seconds=ttl_seconds,
        ) if issuer else None
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=10.0, auth=auth)

    async def resolve(self, secrets_ref: str) -> dict[str, Any]:
        resp = await self._client.post("/v1/secrets/resolve", json={"secrets_ref": secrets_ref})
        resp.raise_for_status()
        return resp.json().get("credentials", {})
