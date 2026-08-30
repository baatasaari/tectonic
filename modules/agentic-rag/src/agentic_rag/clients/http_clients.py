"""HTTP adapters for this module's dependencies: Vector DB, Graph DB,
Knowledge Base (symbolic lookup) and LLM Gateway. Point at the
dependency-stub service until those data-layer modules are deployed for
real; LLM Gateway now exists as Module 3.

Every client below is a `ResilientHTTPClient` (retry + circuit breaker on
every outbound call — see resilience.py).
"""
from __future__ import annotations

import json

import httpx

from agentic_rag.clients.resilience import ResilientHTTPClient
from agentic_rag.core.domain import (
    GroundednessAssessment,
    Provenance,
    RetrievalSource,
    RetrievedItem,
)
from agentic_rag.security.jwt_auth import ServiceBearerAuth

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
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="vector-db", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="vector-db", auth=auth)

    async def search(self, *, query: str, scope: list[str], tenant_id: str) -> list[RetrievedItem]:
        # A genuine module-level gap ticket #82 surfaced standing this module
        # up against a real running Vector DB for the first time: this posted
        # an invented `/v1/vector-db/search {query, scope, tenant_id}` shape.
        # Vector DB's real route is `/v1/vector-db/query` (`QueryRequest`'s
        # real fields: `tenant_id`, `text`, `vector`, `filters`, no bare
        # `scope` concept) with no auth headers this client bothered to send
        # either -- invisible before because every prior test/run stubbed
        # this call. `scope` (this port's own generic string list) has no
        # real analogue in Vector DB's own generic `filters` dict yet; a
        # future slice that needs real scope-restricted retrieval needs a
        # real filter convention agreed with Vector DB first, not one
        # invented unilaterally here.
        resp = await self._post(
            "/v1/vector-db/query",
            json={"tenant_id": tenant_id, "text": query, "filters": {}},
        )
        data = resp.json()
        return [
            RetrievedItem(
                content=r["payload"].get("content", ""),
                source=RetrievalSource.VECTOR_DB,
                provenance=Provenance(
                    source_document=r["payload"].get("document_id", "unknown"), location=r["id"],
                ),
                retrieval_score=r["score"],
            )
            for r in data.get("results", [])
        ]


class HTTPGraphDBClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="graph-db", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="graph-db", auth=auth)

    async def search(self, *, query: str, scope: list[str], tenant_id: str) -> list[RetrievedItem]:
        resp = await self._post("/v1/graph-db/search", json={"query": query, "scope": scope, "tenant_id": tenant_id})
        return _items_from_response(resp.json(), RetrievalSource.GRAPH_DB)


class HTTPKnowledgeBaseClient(ResilientHTTPClient):
    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="knowledge-base", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, timeout=_SHORT_TIMEOUT, breaker_name="knowledge-base", auth=auth)

    async def symbolic_lookup(self, *, query: str, scope: list[str], tenant_id: str) -> list[RetrievedItem]:
        resp = await self._post("/v1/knowledge-base/lookup", json={"query": query, "scope": scope, "tenant_id": tenant_id})
        return _items_from_response(resp.json(), RetrievalSource.KNOWLEDGE_BASE)


class HTTPLLMGatewayClient(ResilientHTTPClient):
    """A genuine module-level gap ticket #82 surfaced standing this module
    up against a real running LLM Gateway for the first time: both methods
    below posted to invented `/v1/rag/assess-groundedness` and
    `/v1/rag/reformulate` paths that LLM Gateway never implemented (and
    never should -- "assess groundedness"/"reformulate a query" are this
    module's own business logic that happens to need a completion, not a
    generic capability LLM Gateway itself should expose as bespoke
    endpoints). LLM Gateway's real, only completion surface is the
    OpenAI-compatible `/v1/llm-gateway/chat/completions` -- same fix, same
    reasoning, as Workflow Engine's own identically-named client class."""

    def __init__(
        self, base_url: str, client: httpx.AsyncClient | None = None, *,
        issuer: str = "", shared_secret: str = "", ttl_seconds: int = 300,
        default_virtual_key: str = "agentic-rag-default",
    ) -> None:
        auth = ServiceBearerAuth(
            issuer=issuer, audience="llm-gateway", shared_secret=shared_secret, ttl_seconds=ttl_seconds,
        ) if issuer else None
        super().__init__(base_url, client=client, breaker_name="llm-gateway", auth=auth)
        self._default_virtual_key = default_virtual_key

    async def _complete(self, *, model: str, prompt_context: dict, tenant_id: str) -> dict:
        resp = await self._post(
            "/v1/llm-gateway/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": json.dumps(prompt_context, default=str)}],
                "routing_hints": {"task_type": "chat"},
            },
            headers={"X-Virtual-Key": self._default_virtual_key, "X-Tenant-Id": tenant_id},
        )
        content = resp.json()["choices"][0]["message"]["content"]
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        return parsed if isinstance(parsed, dict) else {"content": content}

    async def assess_groundedness(self, *, query: str, items: list[RetrievedItem], tenant_id: str) -> GroundednessAssessment:
        data = await self._complete(
            model="rag-groundedness-critic",
            prompt_context={"query": query, "items": [i.content for i in items]},
            tenant_id=tenant_id,
        )
        return GroundednessAssessment(score=data.get("score", 0.0), gaps=data.get("gaps", ""))

    async def reformulate(self, *, query: str, gaps: str, tenant_id: str) -> str:
        data = await self._complete(
            model="rag-query-reformulator", prompt_context={"query": query, "gaps": gaps}, tenant_id=tenant_id,
        )
        return data.get("revised_query", query)
