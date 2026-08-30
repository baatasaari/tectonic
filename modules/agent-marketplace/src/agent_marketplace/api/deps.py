from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request

from agent_marketplace.app_context import AppContext
from agent_marketplace.core.catalogue_service import CatalogueService
from agent_marketplace.core.catalogue_sync_service import CatalogueSyncService
from agent_marketplace.core.governance_service import GovernanceService
from agent_marketplace.core.ports import AgentMarketplaceRepository
from agent_marketplace.core.usage_tracking_service import UsageTrackingService
from agent_marketplace.db.repository import SQLAlchemyAgentMarketplaceRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def resolve_tenant_id(request: Request, ctx: AppContext = Depends(get_ctx)) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


async def get_repository(ctx: AppContext = Depends(get_ctx)) -> AsyncIterator[AgentMarketplaceRepository]:
    async with ctx.session_factory() as session:
        yield SQLAlchemyAgentMarketplaceRepository(session)


def build_governance_service(repository: AgentMarketplaceRepository, ctx: AppContext) -> GovernanceService:
    return GovernanceService(repository, ctx.agent_cards)


def build_catalogue_sync_service(repository: AgentMarketplaceRepository, ctx: AppContext) -> CatalogueSyncService:
    return CatalogueSyncService(repository, ctx.agent_cards)


def build_catalogue_service(repository: AgentMarketplaceRepository) -> CatalogueService:
    return CatalogueService(repository)


def build_usage_tracking_service(repository: AgentMarketplaceRepository) -> UsageTrackingService:
    return UsageTrackingService(repository)
