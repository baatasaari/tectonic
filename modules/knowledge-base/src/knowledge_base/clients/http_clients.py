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
        # A genuine module-level gap ticket #82 surfaced standing this module
        # up against a real running Vector DB for the first time: this posted
        # an invented `/v1/embed-and-store {chunks}` batch shape. Vector DB's
        # real surface is `POST /v1/vector-db/points`, one point (chunk) per
        # call, with `IndexPointRequest`'s real fields -- invisible before
        # because every prior test/run stubbed this call. `vector` is left
        # unset: Vector DB's own VectorService generates the real embedding
        # itself (via its own LLM Gateway client) when none is supplied.
        for chunk in chunks:
            await self._post(
                "/v1/vector-db/points",
                json={
                    "tenant_id": chunk["tenant_id"],
                    "source_module": "knowledge-base",
                    "source_ref": chunk["chunk_id"],
                    "content": chunk["content"],
                    "payload": {
                        "document_id": chunk["document_id"], "document_version_id": chunk["document_version_id"],
                        "policy_tags": chunk["policy_tags"],
                    },
                },
            )


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
