"""HTTP adapter for the LLM Gateway summarisation dependency (Module 3).

`HTTPLLMGatewayClient` is a `ResilientHTTPClient` (retry + circuit breaker
on every outbound call — see resilience.py).
"""
from __future__ import annotations

import httpx

from short_term_memory.clients.resilience import ResilientHTTPClient


class HTTPLLMGatewayClient(ResilientHTTPClient):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, breaker_name="llm-gateway")

    async def summarise(self, text: str, tenant_id: str) -> str:
        resp = await self._post("/v1/summarise", json={"text": text, "tenant_id": tenant_id})
        return resp.json()["summary"]
