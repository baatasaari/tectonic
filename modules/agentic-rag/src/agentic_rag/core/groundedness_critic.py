"""Groundedness Critic (LLD §2.2, differentiator: "self-correcting
retrieval loops"). Scores whether retrieved context actually supports
answering the query, before ever reaching the LLM for the real answer —
catching insufficient grounding at the source rather than downstream in
Guardrails after generation. `method: llm | dedicated_nli_model` per the
LLD's config; the "dedicated_nli_model" slot is filled here by a lightweight
term-overlap heuristic (this build's stand-in for a real NLI model, the
same "no external model-serving dependency" move as Module 5's classifier)
rather than an actual NLI model, with the LLM-backed critic as the default.
"""
from __future__ import annotations

from typing import Protocol

from agentic_rag.core.domain import GroundednessAssessment, RetrievedItem
from agentic_rag.core.ports import LLMGatewayClient
from agentic_rag.core.similarity import cosine_similarity, tokenize


class GroundednessCritic(Protocol):
    async def assess(self, query: str, items: list[RetrievedItem], tenant_id: str) -> GroundednessAssessment: ...


class LLMGroundednessCritic:
    def __init__(self, llm_gateway: LLMGatewayClient) -> None:
        self.llm_gateway = llm_gateway

    async def assess(self, query: str, items: list[RetrievedItem], tenant_id: str) -> GroundednessAssessment:
        return await self.llm_gateway.assess_groundedness(query=query, items=items, tenant_id=tenant_id)


class HeuristicGroundednessCritic:
    """Term-overlap between the query and the retrieved content — a cheap,
    explainable proxy for groundedness when a dedicated NLI model isn't
    configured. Not a claim of real entailment checking."""

    async def assess(self, query: str, items: list[RetrievedItem], tenant_id: str) -> GroundednessAssessment:
        if not items:
            return GroundednessAssessment(score=0.0, gaps="no context retrieved")

        query_vec = tokenize(query)
        combined_vec = tokenize(" ".join(item.content for item in items))
        score = cosine_similarity(query_vec, combined_vec)
        gaps = "" if score >= 0.5 else "retrieved context has low term overlap with the query"
        return GroundednessAssessment(score=score, gaps=gaps)
