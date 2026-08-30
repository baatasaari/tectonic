from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from conversational_engine.app_context import AppContext
from conversational_engine.clients.redis_state_store import RedisSessionStateStore
from conversational_engine.core.ports import ConversationRepository
from conversational_engine.core.session_manager import SessionManager
from conversational_engine.db.repository import SQLAlchemyConversationRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(request: Request) -> AsyncIterator[ConversationRepository]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield SQLAlchemyConversationRepository(session)


def build_session_manager(ctx: AppContext, repository: ConversationRepository) -> SessionManager:
    return SessionManager(
        repository=repository,
        state_store=RedisSessionStateStore(ctx.redis),
        llm_gateway=ctx.llm_gateway,
        guardrails=ctx.guardrails,
        human_oversight=ctx.human_oversight,
        observability=ctx.observability,
        auditability=ctx.auditability,
        settings=ctx.settings,
        workflow_engine=ctx.workflow_engine,
        long_term_memory=ctx.long_term_memory,
    )
