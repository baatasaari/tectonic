from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request

from multi_tenancy.app_context import AppContext
from multi_tenancy.core.isolation_probe_service import IsolationProbeService
from multi_tenancy.core.ports import MultiTenancyRepository
from multi_tenancy.core.tenant_registry_service import TenantRegistryService
from multi_tenancy.db.repository import SQLAlchemyMultiTenancyRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(ctx: AppContext = Depends(get_ctx)) -> AsyncIterator[MultiTenancyRepository]:
    async with ctx.session_factory() as session:
        yield SQLAlchemyMultiTenancyRepository(session)


def build_tenant_registry_service(repository: MultiTenancyRepository) -> TenantRegistryService:
    return TenantRegistryService(repository)


def build_isolation_probe_service(repository: MultiTenancyRepository, ctx: AppContext) -> IsolationProbeService:
    return IsolationProbeService(repository, ctx.probe_clients)
