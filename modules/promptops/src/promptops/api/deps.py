from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request

from promptops.app_context import AppContext
from promptops.core.ab_testing_service import ABTestingService
from promptops.core.drift_detection_service import DriftDetectionService
from promptops.core.ports import PromptOpsRepository
from promptops.core.prompt_registry_service import PromptRegistryService
from promptops.core.reflection_optimiser import ReflectionOptimiser
from promptops.db.repository import SQLAlchemyPromptOpsRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def resolve_tenant_id(request: Request, ctx: AppContext = Depends(get_ctx)) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


async def get_repository(ctx: AppContext = Depends(get_ctx)) -> AsyncIterator[PromptOpsRepository]:
    async with ctx.session_factory() as session:
        yield SQLAlchemyPromptOpsRepository(session)


def build_prompt_registry_service(repository: PromptOpsRepository) -> PromptRegistryService:
    return PromptRegistryService(repository)


def build_ab_testing_service(repository: PromptOpsRepository, ctx: AppContext) -> ABTestingService:
    return ABTestingService(
        repository, ctx.evaluation_framework,
        min_sample_size_per_arm=ctx.settings.min_ab_sample_size_per_arm,
        significance_level=ctx.settings.ab_significance_level,
    )


def build_drift_detection_service(repository: PromptOpsRepository, ctx: AppContext) -> DriftDetectionService:
    return DriftDetectionService(
        repository, ctx.evaluation_framework, significance_level=ctx.settings.drift_significance_level,
    )


def build_reflection_optimiser(repository: PromptOpsRepository, ctx: AppContext) -> ReflectionOptimiser:
    return ReflectionOptimiser(
        repository, ctx.evaluation_framework, ctx.llm_gateway,
        max_pass_rate_before_reflection=ctx.settings.max_pass_rate_before_reflection,
        min_reflection_sample_size=ctx.settings.min_reflection_sample_size,
        reflection_model=ctx.settings.reflection_model,
    )
