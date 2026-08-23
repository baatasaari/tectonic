from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from agentic_rag.app_context import AppContext
from agentic_rag.core.groundedness_critic import (
    GroundednessCritic,
    HeuristicGroundednessCritic,
    LLMGroundednessCritic,
)
from agentic_rag.core.hybrid_retriever import HybridRetriever
from agentic_rag.core.ports import RAGRepository
from agentic_rag.core.query_reformulator import QueryReformulator
from agentic_rag.core.rag_service import RAGService
from agentic_rag.core.retrieval_loop import RetrievalLoop
from agentic_rag.db.repository import SQLAlchemyRAGRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(request: Request) -> AsyncIterator[RAGRepository]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield SQLAlchemyRAGRepository(session)


def _build_critic(ctx: AppContext) -> GroundednessCritic:
    if ctx.settings.critic.method == "heuristic":
        return HeuristicGroundednessCritic()
    return LLMGroundednessCritic(ctx.llm_gateway)


def build_rag_service(ctx: AppContext, repository: RAGRepository) -> RAGService:
    retriever = HybridRetriever(ctx.vector_db, ctx.graph_db, ctx.knowledge_base, ctx.settings.retrieval.hybrid_retrieval_enabled)
    critic = _build_critic(ctx)
    reformulator = QueryReformulator(ctx.llm_gateway)
    loop = RetrievalLoop(retriever, critic, reformulator)
    return RAGService(repository, loop)
