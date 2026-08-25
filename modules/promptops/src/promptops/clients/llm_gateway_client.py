"""HTTP adapter for LLM Gateway (Module 3) -- the other of this
module's two real platform-peer dependencies. Calls that module's own
real `POST /v1/llm-gateway/chat/completions`, the exact endpoint the
Reflection Optimiser uses to draft an improved prompt template -- no
separate/invented LLM client of this module's own.

`HTTPLLMGatewayClient` is a `ResilientHTTPClient` (retry + circuit
breaker on every outbound call — see resilience.py) carrying this
platform's service-to-service JWT (`ServiceBearerAuth`), since LLM
Gateway is a genuine platform peer.
"""
from __future__ import annotations

import httpx

from promptops.clients.resilience import ResilientHTTPClient
from promptops.security.jwt_auth import ServiceBearerAuth

_LONG_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)


class HTTPLLMGatewayClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="llm-gateway", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_LONG_TIMEOUT, breaker_name="llm-gateway", auth=auth)

    async def generate(self, *, tenant_id: str, model: str, prompt: str) -> str:
        resp = await self._post(
            "/v1/llm-gateway/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            headers={"X-Tenant-Id": tenant_id},
        )
        body = resp.json()
        return body["choices"][0]["message"]["content"]
