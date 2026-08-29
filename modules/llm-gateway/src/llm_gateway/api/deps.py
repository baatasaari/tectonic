from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from llm_gateway.app_context import AppContext
from llm_gateway.core.cost_governance import CostGovernanceEngine
from llm_gateway.core.failover import FailoverManager
from llm_gateway.core.gateway_service import LLMGatewayService
from llm_gateway.core.ports import GatewayRepository
from llm_gateway.core.router import QualityAwareRouter
from llm_gateway.db.repository import SQLAlchemyGatewayRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(request: Request) -> AsyncIterator[GatewayRepository]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield SQLAlchemyGatewayRepository(session)


async def build_gateway_service(ctx: AppContext, repository: GatewayRepository) -> LLMGatewayService:
    providers = await repository.list_provider_configs()
    ctx.provider_client.set_providers({p.provider_name: p for p in providers})

    router = QualityAwareRouter(ctx.quality_scores, ctx.settings.routing)
    cost_governance = CostGovernanceEngine(repository, ctx.settings.budget)
    failover = FailoverManager(ctx.provider_client, ctx.settings.failover.max_provider_attempts)
    return LLMGatewayService(
        repository, ctx.cache, router, cost_governance, failover, ctx.settings, multi_tenancy=ctx.multi_tenancy,
    )
