"""HTTP adapter for the LLM Gateway embeddings dependency (Module 3),
called via its OpenAI-compatible API.

`HTTPEmbeddingProvider` is a `ResilientHTTPClient` (retry + circuit
breaker on every outbound call — see resilience.py).
"""
from __future__ import annotations

import httpx

from vector_db.clients.resilience import ResilientHTTPClient
from vector_db.security.jwt_auth import ServiceBearerAuth


class HTTPEmbeddingProvider(ResilientHTTPClient):
    def __init__(
        self, base_url: str, default_model: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
        default_virtual_key: str = "vector-db-default",
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="llm-gateway", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, breaker_name="llm-gateway", auth=auth)
        self._default_model = default_model
        self._default_virtual_key = default_virtual_key

    async def embed(self, text: str, *, model: str | None = None, tenant_id: str = "") -> list[float]:
        # A genuine module-level gap ticket #82 surfaced standing this module
        # up against a real running LLM Gateway for the first time: this
        # posted to an invented `/v1/embeddings` path with no virtual-key/
        # tenant headers at all. LLM Gateway's real embeddings surface is
        # `/v1/llm-gateway/embeddings`, requiring `X-Virtual-Key`/`X-Tenant-Id`
        # headers (LLD §3.3) -- invisible before because every prior test/run
        # stubbed this call.
        resp = await self._post(
            "/v1/llm-gateway/embeddings",
            json={"input": text, "model": model or self._default_model},
            headers={"X-Virtual-Key": self._default_virtual_key, "X-Tenant-Id": tenant_id},
        )
        return resp.json()["data"][0]["embedding"]
