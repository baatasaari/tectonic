from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from sentinel_agents.app_context import AppContext
from sentinel_agents.core.event_processor import SentinelEventProcessor
from sentinel_agents.core.ports import SentinelRepository
from sentinel_agents.db.repository import SQLAlchemySentinelRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(request: Request) -> AsyncIterator[SentinelRepository]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield SQLAlchemySentinelRepository(session)


def build_event_processor(ctx: AppContext, repository: SentinelRepository) -> SentinelEventProcessor:
    return SentinelEventProcessor(
        repository, ctx.workflow_engine, ctx.tool_orchestration, ctx.human_oversight, ctx.auditability,
        ctx.settings, ctx.window_tracker,
    )
