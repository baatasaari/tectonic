from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request

from multi_modality.app_context import AppContext
from multi_modality.core.extraction_service import ExtractionService
from multi_modality.core.extractors import default_extractors
from multi_modality.core.ports import MultiModalityRepository
from multi_modality.db.repository import SQLAlchemyMultiModalityRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def resolve_tenant_id(request: Request, ctx: AppContext = Depends(get_ctx)) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


async def get_repository(ctx: AppContext = Depends(get_ctx)) -> AsyncIterator[MultiModalityRepository]:
    async with ctx.session_factory() as session:
        yield SQLAlchemyMultiModalityRepository(session)


def build_extraction_service(repository: MultiModalityRepository, ctx: AppContext) -> ExtractionService:
    return ExtractionService(repository, ctx.guardrails, default_extractors())
