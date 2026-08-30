"""HTTP adapter for Guardrails (Module 14) -- this module's one real
platform-peer dependency. Reads that module's own `POST
/v1/guardrails/check`, the exact endpoint the groundedness gate runs
against, at `stage=output` with `context` set to the caller-supplied
`grounding_context`.

`HTTPGuardrailsClient` is a `ResilientHTTPClient` (retry + circuit
breaker on every outbound call — see resilience.py) carrying this
platform's service-to-service JWT (`ServiceBearerAuth`), since
Guardrails is a genuine platform peer.
"""
from __future__ import annotations

from typing import Any

import httpx

from multi_modality.clients.resilience import ResilientHTTPClient
from multi_modality.security.jwt_auth import ServiceBearerAuth

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


class HTTPGuardrailsClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="guardrails", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="guardrails", auth=auth)

    async def check_groundedness(self, *, tenant_id: str, text: str, context: str) -> dict[str, Any]:
        resp = await self._post(
            "/v1/guardrails/check",
            json={"text": text, "stage": "output", "context": context},
            headers={"X-Tenant-Id": tenant_id},
        )
        return resp.json()
