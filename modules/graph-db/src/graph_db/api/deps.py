from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from graph_db.app_context import AppContext
from graph_db.core.graph_engine import GraphEngine
from graph_db.core.ports import GraphRepository
from graph_db.db.repository import SQLAlchemyGraphRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(request: Request) -> AsyncIterator[GraphRepository]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield SQLAlchemyGraphRepository(session)


def build_graph_engine(ctx: AppContext, repository: GraphRepository) -> GraphEngine:
    return GraphEngine(repository, ctx.auditability, ctx.settings.query.default_max_traversal_depth)
