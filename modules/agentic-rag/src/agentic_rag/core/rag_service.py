"""RAG Service: persists the retrieval request/hops/result around the
Retrieval Loop — this module's orchestration entry point, same role as the
orchestrators in Modules 1-5.
"""
from __future__ import annotations

from agentic_rag.core.domain import (
    RetrievalHopRecord,
    RetrievalRequestRecord,
    RetrievalResultRecord,
    new_id,
)
from agentic_rag.core.ports import RAGRepository
from agentic_rag.core.retrieval_loop import RetrievalLoop, provenance_chain, synthesize_context
from agentic_rag.telemetry.metrics import (
    rag_groundedness_score,
    rag_hop_count,
    rag_retrievals_total,
)


class RAGService:
    def __init__(self, repository: RAGRepository, loop: RetrievalLoop) -> None:
        self.repository = repository
        self.loop = loop

    async def retrieve(
        self, *, query: str, scope: list[str], tenant_id: str, max_hops: int, groundedness_threshold: float
    ) -> RetrievalResultRecord:
        request = await self.repository.create_request(
            RetrievalRequestRecord(
                id=new_id(), tenant_id=tenant_id, query=query, scope=scope,
                max_hops=max_hops, groundedness_threshold=groundedness_threshold,
            )
        )

        loop_result = await self.loop.run(query, scope, tenant_id, max_hops, groundedness_threshold)

        for hop in loop_result.hops:
            await self.repository.create_hop(
                RetrievalHopRecord(
                    id=new_id(), request_id=request.id, hop_number=hop.hop_number,
                    retrieved_items=hop.retrieved_items, groundedness_score=hop.groundedness_score,
                    reformulated_query=hop.reformulated_query,
                )
            )

        result = RetrievalResultRecord(
            request_id=request.id,
            final_context=synthesize_context(loop_result.best_hop.retrieved_items),
            total_hops=len(loop_result.hops),
            final_groundedness_score=loop_result.best_hop.groundedness_score,
            provenance_chain=provenance_chain(loop_result.best_hop.retrieved_items),
            outcome=loop_result.outcome,
        )
        result = await self.repository.create_result(result)

        rag_retrievals_total.labels(tenant_id=tenant_id, outcome=loop_result.outcome.value).inc()
        rag_hop_count.labels(tenant_id=tenant_id).observe(result.total_hops)
        rag_groundedness_score.labels(tenant_id=tenant_id).observe(result.final_groundedness_score)

        return result
