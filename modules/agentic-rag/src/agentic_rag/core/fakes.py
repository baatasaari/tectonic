"""In-memory fakes for the ports in core/ports.py — the unit-test tier,
mirroring the other modules' core/fakes.py.
"""
from __future__ import annotations

import copy

from agentic_rag.core.domain import (
    GroundednessAssessment,
    Provenance,
    RetrievalHopRecord,
    RetrievalRequestRecord,
    RetrievalResultRecord,
    RetrievalSource,
    RetrievedItem,
)


class InMemoryRAGRepository:
    def __init__(self) -> None:
        self.requests: dict[str, RetrievalRequestRecord] = {}
        self.hops: dict[str, list[RetrievalHopRecord]] = {}
        self.results: dict[str, RetrievalResultRecord] = {}

    async def create_request(self, record: RetrievalRequestRecord) -> RetrievalRequestRecord:
        self.requests[record.id] = copy.deepcopy(record)
        self.hops.setdefault(record.id, [])
        return copy.deepcopy(record)

    async def get_request(self, request_id: str) -> RetrievalRequestRecord | None:
        rec = self.requests.get(request_id)
        return copy.deepcopy(rec) if rec else None

    async def create_hop(self, record: RetrievalHopRecord) -> RetrievalHopRecord:
        self.hops.setdefault(record.request_id, []).append(copy.deepcopy(record))
        return copy.deepcopy(record)

    async def list_hops(self, request_id: str) -> list[RetrievalHopRecord]:
        return [copy.deepcopy(h) for h in self.hops.get(request_id, [])]

    async def create_result(self, record: RetrievalResultRecord) -> RetrievalResultRecord:
        self.results[record.request_id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_result(self, request_id: str) -> RetrievalResultRecord | None:
        rec = self.results.get(request_id)
        return copy.deepcopy(rec) if rec else None


def _item(source: RetrievalSource, doc: str, content: str, score: float = 1.0) -> RetrievedItem:
    return RetrievedItem(content=content, source=source, provenance=Provenance(source_document=doc), retrieval_score=score)


class FakeVectorDBClient:
    def __init__(self) -> None:
        self.canned_results: list[RetrievedItem] | None = None
        self.calls: list[dict] = []

    async def search(self, *, query: str, scope: list[str], tenant_id: str) -> list[RetrievedItem]:
        self.calls.append({"query": query, "scope": scope, "tenant_id": tenant_id})
        if self.canned_results is not None:
            return self.canned_results
        return [_item(RetrievalSource.VECTOR_DB, "vector-doc-1", f"vector passage about: {query}")]


class FakeGraphDBClient:
    def __init__(self) -> None:
        self.canned_results: list[RetrievedItem] | None = None

    async def search(self, *, query: str, scope: list[str], tenant_id: str) -> list[RetrievedItem]:
        if self.canned_results is not None:
            return self.canned_results
        return [_item(RetrievalSource.GRAPH_DB, "graph-doc-1", f"graph relationship about: {query}")]


class FakeKnowledgeBaseClient:
    def __init__(self) -> None:
        self.canned_results: list[RetrievedItem] | None = None

    async def symbolic_lookup(self, *, query: str, scope: list[str], tenant_id: str) -> list[RetrievedItem]:
        if self.canned_results is not None:
            return self.canned_results
        return [_item(RetrievalSource.KNOWLEDGE_BASE, "kb-doc-1", f"structured fact about: {query}")]


class StubLLMGatewayClient:
    def __init__(self) -> None:
        self.groundedness_scores: list[float] = [0.9]  # popped in order across successive assess() calls
        self.reformulated_query = "revised query"
        self.assess_calls: list[dict] = []
        self.reformulate_calls: list[dict] = []

    async def assess_groundedness(self, *, query: str, items: list[RetrievedItem], tenant_id: str) -> GroundednessAssessment:
        self.assess_calls.append({"query": query, "items": items, "tenant_id": tenant_id})
        score = self.groundedness_scores[len(self.assess_calls) - 1] if len(self.assess_calls) <= len(self.groundedness_scores) else self.groundedness_scores[-1]
        gaps = "" if score >= 0.85 else "missing supporting detail"
        return GroundednessAssessment(score=score, gaps=gaps)

    async def reformulate(self, *, query: str, gaps: str, tenant_id: str) -> str:
        self.reformulate_calls.append({"query": query, "gaps": gaps, "tenant_id": tenant_id})
        return self.reformulated_query
