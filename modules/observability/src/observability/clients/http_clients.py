"""HTTP adapter for this module's LLM Gateway dependency (reasoning-trace
narrative generation).

`HTTPLLMGatewayClient` is a `ResilientHTTPClient` (retry + circuit
breaker on every outbound call — see resilience.py).
"""
from __future__ import annotations

import httpx

from observability.clients.resilience import ResilientHTTPClient


class HTTPLLMGatewayClient(ResilientHTTPClient):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, breaker_name="llm-gateway")

    async def narrate(self, trace_summary: list[dict]) -> str:
        resp = await self._post("/v1/narrate", json={"trace_summary": trace_summary})
        return resp.json()["narrative"]
