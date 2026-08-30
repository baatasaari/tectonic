from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from long_term_memory.app_context import AppContext
from long_term_memory.core.consent_service import ConsentService
from long_term_memory.core.consolidation import ConsolidationEngine
from long_term_memory.core.forgetting import ForgettingEngine
from long_term_memory.core.legal_hold_service import LegalHoldService
from long_term_memory.core.memory_service import MemoryService
from long_term_memory.core.ports import LongTermMemoryRepository
from long_term_memory.core.reflection import ReflectionLoop
from long_term_memory.db.repository import SQLAlchemyLongTermMemoryRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(request: Request) -> AsyncIterator[LongTermMemoryRepository]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield SQLAlchemyLongTermMemoryRepository(session)


def build_memory_service(ctx: AppContext, repository: LongTermMemoryRepository) -> MemoryService:
    return MemoryService(repository, ctx.vector_db, ctx.graph_db, ctx.guardrails, ctx.settings.cross_agent_sharing)


def build_reflection_loop(ctx: AppContext, repository: LongTermMemoryRepository) -> ReflectionLoop:
    return ReflectionLoop(repository, ctx.llm_gateway)


def build_forgetting_engine(ctx: AppContext, repository: LongTermMemoryRepository) -> ForgettingEngine:
    return ForgettingEngine(repository, ctx.vector_db, ctx.graph_db)


def build_consolidation_engine(ctx: AppContext, repository: LongTermMemoryRepository) -> ConsolidationEngine:
    return ConsolidationEngine(repository, ctx.settings.consolidation.decay_threshold)


def build_consent_service(repository: LongTermMemoryRepository) -> ConsentService:
    return ConsentService(repository)


def build_legal_hold_service(repository: LongTermMemoryRepository) -> LegalHoldService:
    return LegalHoldService(repository)
