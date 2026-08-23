"""HTTP adapters for this module's downstream dependencies: Vector DB
(Module 10) and Graph DB.
"""
from __future__ import annotations

from typing import Any

import httpx


class HTTPVectorDBClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=60.0)

    async def embed_and_store(self, chunks: list[dict[str, Any]]) -> None:
        resp = await self._client.post("/v1/embed-and-store", json={"chunks": chunks})
        resp.raise_for_status()


class HTTPGraphDBClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=60.0)

    async def extract_entities(self, chunks: list[dict[str, Any]]) -> None:
        resp = await self._client.post("/v1/extract-entities", json={"chunks": chunks})
        resp.raise_for_status()
