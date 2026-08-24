"""HTTP adapters for this module's downstream dependencies: Vector DB
(Module 10) and Graph DB.
"""
from __future__ import annotations

from typing import Any

import httpx

from knowledge_base.security.jwt_auth import ServiceBearerAuth


class HTTPVectorDBClient:
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="vector-db", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=60.0, auth=auth)

    async def embed_and_store(self, chunks: list[dict[str, Any]]) -> None:
        resp = await self._client.post("/v1/embed-and-store", json={"chunks": chunks})
        resp.raise_for_status()


class HTTPGraphDBClient:
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="graph-db", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=60.0, auth=auth)

    async def extract_entities(self, chunks: list[dict[str, Any]]) -> None:
        resp = await self._client.post("/v1/extract-entities", json={"chunks": chunks})
        resp.raise_for_status()
