"""HTTP adapter for the LLM Gateway summarisation dependency (Module 3)."""
from __future__ import annotations

import httpx


class HTTPLLMGatewayClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=30.0)

    async def summarise(self, text: str, tenant_id: str) -> str:
        resp = await self._client.post("/v1/summarise", json={"text": text, "tenant_id": tenant_id})
        resp.raise_for_status()
        return resp.json()["summary"]
