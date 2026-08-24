"""HTTP adapter for the LLM Gateway summarisation dependency (Module 3)."""
from __future__ import annotations

import httpx

from short_term_memory.security.jwt_auth import ServiceBearerAuth


class HTTPLLMGatewayClient:
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="llm-gateway", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=30.0, auth=auth)

    async def summarise(self, text: str, tenant_id: str) -> str:
        resp = await self._client.post("/v1/summarise", json={"text": text, "tenant_id": tenant_id})
        resp.raise_for_status()
        return resp.json()["summary"]
