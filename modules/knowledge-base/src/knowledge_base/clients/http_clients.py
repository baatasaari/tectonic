"""HTTP adapters for this module's downstream dependencies: Vector DB
(Module 10) and Graph DB.

Every client below is a `ResilientHTTPClient` (retry + circuit breaker on
every outbound call — see resilience.py).
"""
from __future__ import annotations

from typing import Any

import httpx

from knowledge_base.clients.resilience import ResilientHTTPClient
from knowledge_base.security.jwt_auth import ServiceBearerAuth

_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)


class HTTPVectorDBClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="vector-db", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_TIMEOUT, breaker_name="vector-db", auth=auth)

    async def embed_and_store(self, chunks: list[dict[str, Any]]) -> None:
        await self._post("/v1/embed-and-store", json={"chunks": chunks})


class HTTPGraphDBClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="graph-db", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_TIMEOUT, breaker_name="graph-db", auth=auth)

    async def extract_entities(self, chunks: list[dict[str, Any]]) -> None:
        await self._post("/v1/extract-entities", json={"chunks": chunks})
