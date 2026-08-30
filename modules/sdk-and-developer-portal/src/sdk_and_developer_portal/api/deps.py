from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request

from sdk_and_developer_portal.app_context import AppContext
from sdk_and_developer_portal.core.adoption_metrics_service import AdoptionMetricsService
from sdk_and_developer_portal.core.developer_account_service import DeveloperAccountService
from sdk_and_developer_portal.core.module_catalog_service import ModuleCatalogService
from sdk_and_developer_portal.core.ports import PortalRepository
from sdk_and_developer_portal.core.sdk_generator_service import SdkGeneratorService
from sdk_and_developer_portal.db.repository import SQLAlchemyPortalRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def resolve_tenant_id(request: Request, ctx: AppContext = Depends(get_ctx)) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


async def get_repository(ctx: AppContext = Depends(get_ctx)) -> AsyncIterator[PortalRepository]:
    async with ctx.session_factory() as session:
        yield SQLAlchemyPortalRepository(session)


def build_developer_account_service(repository: PortalRepository, ctx: AppContext) -> DeveloperAccountService:
    return DeveloperAccountService(repository, ctx.identity_access, ctx.multi_tenancy)


def build_module_catalog_service(repository: PortalRepository, ctx: AppContext) -> ModuleCatalogService:
    return ModuleCatalogService(repository, ctx.module_spec)


def build_sdk_generator_service(repository: PortalRepository, ctx: AppContext) -> SdkGeneratorService:
    return SdkGeneratorService(repository, build_module_catalog_service(repository, ctx))


def build_adoption_metrics_service(repository: PortalRepository, ctx: AppContext) -> AdoptionMetricsService:
    return AdoptionMetricsService(repository, ctx.auditability)
