"""HTTP adapter for the LLM Gateway summarisation dependency (Module 3).

`HTTPLLMGatewayClient` is a `ResilientHTTPClient` (retry + circuit breaker
on every outbound call — see resilience.py).
"""
from __future__ import annotations

import httpx

class HTTPLLMGatewayClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="llm-gateway", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, breaker_name="llm-gateway", auth=auth)

    async def summarise(self, text: str, tenant_id: str) -> str:
        resp = await self._post("/v1/summarise", json={"text": text, "tenant_id": tenant_id})
        return resp.json()["summary"]
