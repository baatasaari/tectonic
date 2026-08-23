"""Hybrid Retriever (LLD §2.2, differentiator: "hybrid symbolic-vector
retrieval"). Queries Vector DB, Graph DB and Knowledge Base's symbolic
lookup concurrently and merges results via reciprocal rank fusion — a
retriever combining approximate (vector) and exact (symbolic) matches
shouldn't let one backend's score scale dominate the other's, which is
exactly what RRF avoids by fusing on rank rather than raw score.
"""
from __future__ import annotations

import asyncio

from agentic_rag.core.domain import RetrievedItem
from agentic_rag.core.ports import GraphDBClient, KnowledgeBaseClient, VectorDBClient

_RRF_K = 60  # standard RRF damping constant


def _item_key(item: RetrievedItem) -> tuple[str, str]:
    return (item.provenance.source_document, item.provenance.location)


def reciprocal_rank_fusion(result_lists: list[list[RetrievedItem]]) -> list[RetrievedItem]:
    scores: dict[tuple[str, str], float] = {}
    items_by_key: dict[tuple[str, str], RetrievedItem] = {}

    for results in result_lists:
        for rank, item in enumerate(results, start=1):
            key = _item_key(item)
            scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + rank)
            if key not in items_by_key:
                items_by_key[key] = item

    ranked_keys = sorted(scores, key=lambda k: scores[k], reverse=True)
    fused = []
    for key in ranked_keys:
        item = items_by_key[key]
        fused.append(RetrievedItem(
            content=item.content, source=item.source, provenance=item.provenance, retrieval_score=scores[key]
        ))
    return fused


class HybridRetriever:
    def __init__(
        self,
        vector_db: VectorDBClient,
        graph_db: GraphDBClient,
        knowledge_base: KnowledgeBaseClient,
        hybrid_enabled: bool = True,
    ) -> None:
        self.vector_db = vector_db
        self.graph_db = graph_db
        self.knowledge_base = knowledge_base
        self.hybrid_enabled = hybrid_enabled

    async def retrieve(self, query: str, scope: list[str], tenant_id: str) -> list[RetrievedItem]:
        if not self.hybrid_enabled:
            return await self.vector_db.search(query=query, scope=scope, tenant_id=tenant_id)

        vector_results, graph_results, symbolic_results = await asyncio.gather(
            self.vector_db.search(query=query, scope=scope, tenant_id=tenant_id),
            self.graph_db.search(query=query, scope=scope, tenant_id=tenant_id),
            self.knowledge_base.symbolic_lookup(query=query, scope=scope, tenant_id=tenant_id),
        )
        return reciprocal_rank_fusion([vector_results, graph_results, symbolic_results])
