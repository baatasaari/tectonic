"""HTTP adapter for the LLM Gateway embeddings dependency (Module 3),
called via its OpenAI-compatible API.

`HTTPEmbeddingProvider` is a `ResilientHTTPClient` (retry + circuit
breaker on every outbound call — see resilience.py).
"""
from __future__ import annotations

import httpx

from vector_db.clients.resilience import ResilientHTTPClient


class HTTPEmbeddingProvider(ResilientHTTPClient):
    def __init__(self, base_url: str, default_model: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, breaker_name="llm-gateway")
        self._default_model = default_model

    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        resp = await self._post("/v1/embeddings", json={"input": text, "model": model or self._default_model})
        return resp.json()["data"][0]["embedding"]
