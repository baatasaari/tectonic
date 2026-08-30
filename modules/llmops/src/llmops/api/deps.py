from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request

from llmops.app_context import AppContext
from llmops.core.canary_evaluation_service import CanaryEvaluationService
from llmops.core.model_registry_service import ModelRegistryService
from llmops.core.ports import LLMOpsRepository
from llmops.core.rollout_service import RolloutService
from llmops.db.repository import SQLAlchemyLLMOpsRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def resolve_tenant_id(request: Request, ctx: AppContext = Depends(get_ctx)) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


async def get_repository(ctx: AppContext = Depends(get_ctx)) -> AsyncIterator[LLMOpsRepository]:
    async with ctx.session_factory() as session:
        yield SQLAlchemyLLMOpsRepository(session)


def build_model_registry_service(repository: LLMOpsRepository) -> ModelRegistryService:
    return ModelRegistryService(repository)


def build_canary_evaluation_service(ctx: AppContext) -> CanaryEvaluationService:
    return CanaryEvaluationService(
        ctx.evaluation_framework, min_sample_size=ctx.settings.min_canary_sample_size,
        min_pass_rate=ctx.settings.min_canary_pass_rate,
    )


def build_rollout_service(repository: LLMOpsRepository, ctx: AppContext) -> RolloutService:
    return RolloutService(repository, build_canary_evaluation_service(ctx))
