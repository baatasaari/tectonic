"""Retrieve-Critique-Reformulate Loop (LLD §2.2, §3.4, §3.6): orchestrates
the Hybrid Retriever, Groundedness Critic and Query Reformulator until the
groundedness threshold is met or max hops is reached. The LLD assigns this
role to an ADK 2.0 Workflow Runtime loop node; implemented here as a
bounded async loop with the same termination semantics (groundedness
threshold met or max iterations reached) — same "behind a port, ADK is a
pluggable production choice" boundary Module 1 establishes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from agentic_rag.core.domain import Provenance, RetrievalOutcome, RetrievedItem
from agentic_rag.core.groundedness_critic import GroundednessCritic
from agentic_rag.core.hybrid_retriever import HybridRetriever
from agentic_rag.core.query_reformulator import QueryReformulator
from agentic_rag.telemetry.metrics import rag_retrieval_duration_seconds


@dataclass
class HopOutcome:
    hop_number: int
    query_used: str
    reformulated_query: str | None
    retrieved_items: list[RetrievedItem]
    groundedness_score: float


@dataclass
class LoopResult:
    hops: list[HopOutcome]
    outcome: RetrievalOutcome
    best_hop: HopOutcome


class RetrievalLoop:
    def __init__(
        self, retriever: HybridRetriever, critic: GroundednessCritic, reformulator: QueryReformulator
    ) -> None:
        self.retriever = retriever
        self.critic = critic
        self.reformulator = reformulator

    async def run(
        self, initial_query: str, scope: list[str], tenant_id: str, max_hops: int, groundedness_threshold: float
    ) -> LoopResult:
        hops: list[HopOutcome] = []
        query = initial_query
        reformulated_query: str | None = None
        best_hop: HopOutcome | None = None

        for hop_number in range(1, max_hops + 1):
            hop_start = time.perf_counter()
            items = await self.retriever.retrieve(query, scope, tenant_id)
            assessment = await self.critic.assess(query, items, tenant_id)
            rag_retrieval_duration_seconds.labels(tenant_id=tenant_id, hop_number=str(hop_number)).observe(
                time.perf_counter() - hop_start
            )

            hop = HopOutcome(
                hop_number=hop_number, query_used=query, reformulated_query=reformulated_query,
                retrieved_items=items, groundedness_score=assessment.score,
            )
            hops.append(hop)
            if best_hop is None or hop.groundedness_score > best_hop.groundedness_score:
                best_hop = hop

            if assessment.score >= groundedness_threshold:
                return LoopResult(hops=hops, outcome=RetrievalOutcome.SUFFICIENT, best_hop=best_hop)

            if hop_number == max_hops:
                return LoopResult(hops=hops, outcome=RetrievalOutcome.MAX_HOPS_REACHED, best_hop=best_hop)

            reformulated_query = await self.reformulator.reformulate(query, assessment.gaps, tenant_id)
            query = reformulated_query

        # Unreachable given max_hops >= 1, but keeps the type checker (and a
        # future refactor) honest about every path returning a LoopResult.
        return LoopResult(hops=hops, outcome=RetrievalOutcome.MAX_HOPS_REACHED, best_hop=best_hop or hops[-1])


def synthesize_context(items: list[RetrievedItem]) -> str:
    return "\n\n".join(item.content for item in items)


def provenance_chain(items: list[RetrievedItem]) -> list[Provenance]:
    return [item.provenance for item in items]
