from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request

from agent_cards.app_context import AppContext
from agent_cards.core.discovery_service import DiscoveryService
from agent_cards.core.ports import AgentCardsRepository
from agent_cards.core.registry_service import RegistryService
from agent_cards.core.trust_score_calculator import TrustScoreCalculator
from agent_cards.db.repository import SQLAlchemyAgentCardsRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def resolve_tenant_id(request: Request, ctx: AppContext = Depends(get_ctx)) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


async def get_repository(ctx: AppContext = Depends(get_ctx)) -> AsyncIterator[AgentCardsRepository]:
    async with ctx.session_factory() as session:
        yield SQLAlchemyAgentCardsRepository(session)


def build_registry_service(repository: AgentCardsRepository) -> RegistryService:
    return RegistryService(repository)


def build_discovery_service(repository: AgentCardsRepository, ctx: AppContext) -> DiscoveryService:
    return DiscoveryService(repository, staleness_ttl_seconds=ctx.settings.card_staleness_ttl_seconds)


def build_trust_score_calculator(repository: AgentCardsRepository, ctx: AppContext) -> TrustScoreCalculator:
    return TrustScoreCalculator(
        repository, ctx.evaluation_framework, ctx.regulatory_compliance,
        performance_weight=ctx.settings.performance_weight, compliance_weight=ctx.settings.compliance_weight,
        compliance_framework_name=ctx.settings.compliance_framework_name,
    )
