"""HTTP adapter for the LLM Gateway embeddings dependency (Module 3),
called via its OpenAI-compatible API.
"""
from __future__ import annotations

import httpx

from vector_db.security.jwt_auth import ServiceBearerAuth


class HTTPEmbeddingProvider:
    def __init__(
        self, base_url: str, default_model: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="llm-gateway", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=30.0, auth=auth)
        self._default_model = default_model

    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        resp = await self._client.post(
            "/v1/embeddings", json={"input": text, "model": model or self._default_model}
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]
