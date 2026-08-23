from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from knowledge_base.app_context import AppContext
from knowledge_base.core.ingestion_service import IngestionService
from knowledge_base.core.ports import KnowledgeBaseRepository
from knowledge_base.db.repository import SQLAlchemyKnowledgeBaseRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(request: Request) -> AsyncIterator[KnowledgeBaseRepository]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield SQLAlchemyKnowledgeBaseRepository(session)


def build_ingestion_service(ctx: AppContext, repository: KnowledgeBaseRepository) -> IngestionService:
    return IngestionService(
        repository, ctx.blob_storage, ctx.vector_db, ctx.graph_db, ctx.settings.chunking, ctx.settings.staleness,
    )
