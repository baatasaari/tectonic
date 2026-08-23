"""HTTP adapter for this module's LLM Gateway dependency (reasoning-trace
narrative generation)."""
from __future__ import annotations

import httpx


class HTTPLLMGatewayClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=30.0)

    async def narrate(self, trace_summary: list[dict]) -> str:
        resp = await self._client.post("/v1/narrate", json={"trace_summary": trace_summary})
        resp.raise_for_status()
        return resp.json()["narrative"]
