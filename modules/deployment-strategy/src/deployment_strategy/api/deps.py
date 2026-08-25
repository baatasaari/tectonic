from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request

from deployment_strategy.app_context import AppContext
from deployment_strategy.core.canary_health_calculator import CanaryHealthCalculator
from deployment_strategy.core.ports import DeploymentStrategyRepository
from deployment_strategy.core.rollout_service import RolloutService
from deployment_strategy.db.repository import SQLAlchemyDeploymentStrategyRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def resolve_tenant_id(request: Request, ctx: AppContext = Depends(get_ctx)) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


async def get_repository(ctx: AppContext = Depends(get_ctx)) -> AsyncIterator[DeploymentStrategyRepository]:
    async with ctx.session_factory() as session:
        yield SQLAlchemyDeploymentStrategyRepository(session)


def build_canary_health_calculator(ctx: AppContext) -> CanaryHealthCalculator:
    return CanaryHealthCalculator(
        ctx.evaluation_framework, ctx.finops,
        min_groundedness_sample_size=ctx.settings.min_groundedness_sample_size,
        min_health_score=ctx.settings.min_health_score,
        groundedness_weight=ctx.settings.groundedness_weight,
        cost_weight=ctx.settings.cost_weight,
        budget_period=ctx.settings.budget_period,
    )


def build_rollout_service(repository: DeploymentStrategyRepository, ctx: AppContext) -> RolloutService:
    return RolloutService(repository, build_canary_health_calculator(ctx))
