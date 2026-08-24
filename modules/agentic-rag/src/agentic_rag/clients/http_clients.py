"""HTTP adapters for this module's dependencies: Vector DB, Graph DB,
Knowledge Base (symbolic lookup) and LLM Gateway. Point at the
dependency-stub service until those data-layer modules are deployed for
real; LLM Gateway now exists as Module 3.

Every client below is a `ResilientHTTPClient` (retry + circuit breaker on
every outbound call — see resilience.py).
"""
from __future__ import annotations

import httpx

from agentic_rag.clients.resilience import ResilientHTTPClient
from agentic_rag.core.domain import (
    GroundednessAssessment,
    Provenance,
    RetrievalSource,
    RetrievedItem,
)

_SHORT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


def _items_from_response(data: dict, source: RetrievalSource) -> list[RetrievedItem]:
    return [
        RetrievedItem(
            content=r["content"],
            source=source,
            provenance=Provenance(**r.get("provenance", {"source_document": "unknown"})),
            retrieval_score=r.get("score", 0.0),
        )
        for r in data.get("results", [])
    ]


class HTTPVectorDBClient(ResilientHTTPClient):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="vector-db")

    async def search(self, *, query: str, scope: list[str], tenant_id: str) -> list[RetrievedItem]:
        resp = await self._post("/v1/vector-db/search", json={"query": query, "scope": scope, "tenant_id": tenant_id})
        return _items_from_response(resp.json(), RetrievalSource.VECTOR_DB)


class HTTPGraphDBClient(ResilientHTTPClient):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="graph-db")

    async def search(self, *, query: str, scope: list[str], tenant_id: str) -> list[RetrievedItem]:
        resp = await self._post("/v1/graph-db/search", json={"query": query, "scope": scope, "tenant_id": tenant_id})
        return _items_from_response(resp.json(), RetrievalSource.GRAPH_DB)


class HTTPKnowledgeBaseClient(ResilientHTTPClient):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="knowledge-base")

    async def symbolic_lookup(self, *, query: str, scope: list[str], tenant_id: str) -> list[RetrievedItem]:
        resp = await self._post("/v1/knowledge-base/lookup", json={"query": query, "scope": scope, "tenant_id": tenant_id})
        return _items_from_response(resp.json(), RetrievalSource.KNOWLEDGE_BASE)


class HTTPLLMGatewayClient(ResilientHTTPClient):
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(base_url, client=client, breaker_name="llm-gateway")

    async def assess_groundedness(self, *, query: str, items: list[RetrievedItem], tenant_id: str) -> GroundednessAssessment:
        resp = await self._post(
            "/v1/rag/assess-groundedness",
            json={"query": query, "items": [i.content for i in items], "tenant_id": tenant_id},
        )
        data = resp.json()
        return GroundednessAssessment(score=data["score"], gaps=data.get("gaps", ""))

    async def reformulate(self, *, query: str, gaps: str, tenant_id: str) -> str:
        resp = await self._post("/v1/rag/reformulate", json={"query": query, "gaps": gaps, "tenant_id": tenant_id})
        return resp.json()["revised_query"]
