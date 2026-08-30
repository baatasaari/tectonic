from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request

from multi_tenancy.app_context import AppContext
from multi_tenancy.core.environment_service import EnvironmentService
from multi_tenancy.core.isolation_probe_service import IsolationProbeService
from multi_tenancy.core.organisation_service import OrganisationService
from multi_tenancy.core.ports import MultiTenancyRepository
from multi_tenancy.core.quota_service import QuotaEnforcementService, QuotaSetService
from multi_tenancy.core.residency_policy_service import ResidencyPolicyService
from multi_tenancy.core.resource_allocation_service import ResourceAllocationService
from multi_tenancy.core.tenant_registry_service import TenantRegistryService
from multi_tenancy.core.workspace_service import WorkspaceService
from multi_tenancy.db.repository import SQLAlchemyMultiTenancyRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(ctx: AppContext = Depends(get_ctx)) -> AsyncIterator[MultiTenancyRepository]:
    async with ctx.session_factory() as session:
        yield SQLAlchemyMultiTenancyRepository(session)


def build_tenant_registry_service(repository: MultiTenancyRepository, ctx: AppContext) -> TenantRegistryService:
    return TenantRegistryService(repository, ctx.auditability)


def build_isolation_probe_service(repository: MultiTenancyRepository, ctx: AppContext) -> IsolationProbeService:
    return IsolationProbeService(repository, ctx.probe_clients)


def build_organisation_service(repository: MultiTenancyRepository, ctx: AppContext) -> OrganisationService:
    return OrganisationService(repository, ctx.auditability)


def build_workspace_service(repository: MultiTenancyRepository, ctx: AppContext) -> WorkspaceService:
    return WorkspaceService(repository, ctx.auditability)


def build_environment_service(repository: MultiTenancyRepository, ctx: AppContext) -> EnvironmentService:
    return EnvironmentService(repository, ctx.auditability)


def build_quota_set_service(repository: MultiTenancyRepository, ctx: AppContext) -> QuotaSetService:
    return QuotaSetService(repository)


def build_quota_enforcement_service(repository: MultiTenancyRepository, ctx: AppContext) -> QuotaEnforcementService:
    return QuotaEnforcementService(repository)


def build_resource_allocation_service(repository: MultiTenancyRepository, ctx: AppContext) -> ResourceAllocationService:
    return ResourceAllocationService(repository, ctx.auditability)


def build_residency_policy_service(repository: MultiTenancyRepository, ctx: AppContext) -> ResidencyPolicyService:
    return ResidencyPolicyService(repository)
