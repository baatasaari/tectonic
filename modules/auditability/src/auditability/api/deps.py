from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from auditability.app_context import AppContext
from auditability.core.ingestion_service import IngestionService
from auditability.core.nl_query_translator import NLQueryTranslator
from auditability.core.ports import AuditabilityRepository
from auditability.db.repository import SQLAlchemyAuditabilityRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(request: Request) -> AsyncIterator[AuditabilityRepository]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield SQLAlchemyAuditabilityRepository(session)


def build_ingestion_service(repository: AuditabilityRepository) -> IngestionService:
    return IngestionService(repository)


def build_nl_query_translator(ctx: AppContext) -> NLQueryTranslator:
    return NLQueryTranslator(ctx.llm_gateway)
