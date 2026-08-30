"""HTTP adapter for this module's one external dependency: LLM Gateway,
used only for natural-language query translation (`POST /query`) — audit
ingestion, listing, chain verification and audit-pack generation all stay
entirely within this module.

`HTTPLLMGatewayClient` is a `ResilientHTTPClient` (retry + circuit
breaker on every outbound call — see resilience.py).
"""
from __future__ import annotations

from typing import Any

import httpx

from auditability.clients.resilience import ResilientHTTPClient
from auditability.security.jwt_auth import ServiceBearerAuth

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


class HTTPLLMGatewayClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="llm-gateway", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="llm-gateway", auth=auth)

    async def complete(self, *, prompt_context: dict[str, Any], tenant_id: str) -> dict[str, Any]:
        resp = await self._post("/v1/completions", json={"context": prompt_context, "tenant_id": tenant_id})
        return resp.json()["proposal"]
