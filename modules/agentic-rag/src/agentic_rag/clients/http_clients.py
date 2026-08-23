"""HTTP adapters for this module's dependencies: Vector DB, Graph DB,
Knowledge Base (symbolic lookup) and LLM Gateway. Point at the
dependency-stub service until those data-layer modules are deployed for
real; LLM Gateway now exists as Module 3.
"""
from __future__ import annotations

import httpx

from agentic_rag.core.domain import (
    GroundednessAssessment,
    Provenance,
    RetrievalSource,
    RetrievedItem,
)


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


class HTTPVectorDBClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def search(self, *, query: str, scope: list[str], tenant_id: str) -> list[RetrievedItem]:
        resp = await self._client.post("/v1/vector-db/search", json={"query": query, "scope": scope, "tenant_id": tenant_id})
        resp.raise_for_status()
        return _items_from_response(resp.json(), RetrievalSource.VECTOR_DB)


class HTTPGraphDBClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def search(self, *, query: str, scope: list[str], tenant_id: str) -> list[RetrievedItem]:
        resp = await self._client.post("/v1/graph-db/search", json={"query": query, "scope": scope, "tenant_id": tenant_id})
        resp.raise_for_status()
        return _items_from_response(resp.json(), RetrievalSource.GRAPH_DB)


class HTTPKnowledgeBaseClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def symbolic_lookup(self, *, query: str, scope: list[str], tenant_id: str) -> list[RetrievedItem]:
        resp = await self._client.post(
            "/v1/knowledge-base/lookup", json={"query": query, "scope": scope, "tenant_id": tenant_id}
        )
        resp.raise_for_status()
        return _items_from_response(resp.json(), RetrievalSource.KNOWLEDGE_BASE)


class HTTPLLMGatewayClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=30.0)

    async def assess_groundedness(self, *, query: str, items: list[RetrievedItem], tenant_id: str) -> GroundednessAssessment:
        resp = await self._client.post(
            "/v1/rag/assess-groundedness",
            json={"query": query, "items": [i.content for i in items], "tenant_id": tenant_id},
        )
        resp.raise_for_status()
        data = resp.json()
        return GroundednessAssessment(score=data["score"], gaps=data.get("gaps", ""))

    async def reformulate(self, *, query: str, gaps: str, tenant_id: str) -> str:
        resp = await self._client.post(
            "/v1/rag/reformulate", json={"query": query, "gaps": gaps, "tenant_id": tenant_id}
        )
        resp.raise_for_status()
        return resp.json()["revised_query"]
