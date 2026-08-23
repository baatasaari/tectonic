from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from intent_detection.app_context import AppContext
from intent_detection.core.classification_service import ClassificationService
from intent_detection.core.llm_fallback import LLMFallbackHandler
from intent_detection.core.ports import IntentRepository
from intent_detection.db.repository import SQLAlchemyIntentRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(request: Request) -> AsyncIterator[IntentRepository]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield SQLAlchemyIntentRepository(session)


def build_classification_service(ctx: AppContext, repository: IntentRepository) -> ClassificationService:
    fallback_handler = LLMFallbackHandler(ctx.llm_gateway)
    return ClassificationService(repository, ctx.primary_classifier, ctx.decomposer, fallback_handler, ctx.settings.classification)
