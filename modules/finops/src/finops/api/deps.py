from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request

from finops.app_context import AppContext
from finops.core.budget_policy_service import BudgetPolicyService
from finops.core.cost_optimisation_agent import CostOptimisationAgent
from finops.core.forecasting_service import ForecastingService
from finops.core.ports import FinOpsRepository
from finops.core.usage_aggregation_service import UsageAggregationService
from finops.db.repository import SQLAlchemyFinOpsRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def resolve_tenant_id(request: Request, ctx: AppContext = Depends(get_ctx)) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


async def get_repository(ctx: AppContext = Depends(get_ctx)) -> AsyncIterator[FinOpsRepository]:
    async with ctx.session_factory() as session:
        yield SQLAlchemyFinOpsRepository(session)


def build_budget_policy_service(repository: FinOpsRepository) -> BudgetPolicyService:
    return BudgetPolicyService(repository)


def build_usage_aggregation_service(repository: FinOpsRepository, ctx: AppContext) -> UsageAggregationService:
    return UsageAggregationService(repository, ctx.llm_gateway)


def build_cost_optimisation_agent(repository: FinOpsRepository, ctx: AppContext) -> CostOptimisationAgent:
    return CostOptimisationAgent(
        repository, build_usage_aggregation_service(repository, ctx), ForecastingService(),
        min_alert_threshold_pct=ctx.settings.min_alert_threshold_pct,
        alert_threshold_step=ctx.settings.alert_threshold_step,
    )
