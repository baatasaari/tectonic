"""SQLAlchemy-backed implementation of MultiTenancyRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from multi_tenancy.core.domain import (
    EnvironmentRecord,
    HierarchyStatus,
    IsolationProbeResult,
    OrganisationRecord,
    TenantEntitlementRecord,
    TenantRecord,
    TenantStatus,
    WorkspaceRecord,
)
from multi_tenancy.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _tenant_to_domain(m: models.Tenant) -> TenantRecord:
    return TenantRecord(
        id=str(m.id), name=m.name, status=TenantStatus(m.status), tier=m.tier,
        organisation_id=str(m.organisation_id) if m.organisation_id else None,
        entitlements_configured_at=_as_utc(m.entitlements_configured_at),
        created_at=_as_utc(m.created_at), updated_at=_as_utc(m.updated_at),
    )


def _organisation_to_domain(m: models.Organisation) -> OrganisationRecord:
    return OrganisationRecord(
        id=str(m.id), name=m.name, status=HierarchyStatus(m.status), owner_identity_id=m.owner_identity_id,
        labels=dict(m.labels or {}), version=m.version,
        created_at=_as_utc(m.created_at), updated_at=_as_utc(m.updated_at),
    )


def _workspace_to_domain(m: models.Workspace) -> WorkspaceRecord:
    return WorkspaceRecord(
        id=str(m.id), tenant_id=str(m.tenant_id), name=m.name, status=HierarchyStatus(m.status),
        owner_identity_id=m.owner_identity_id, labels=dict(m.labels or {}), version=m.version,
        created_at=_as_utc(m.created_at), updated_at=_as_utc(m.updated_at),
    )


def _environment_to_domain(m: models.Environment) -> EnvironmentRecord:
    return EnvironmentRecord(
        id=str(m.id), workspace_id=str(m.workspace_id), name=m.name, kind=m.kind, region=m.region,
        status=HierarchyStatus(m.status), owner_identity_id=m.owner_identity_id,
        labels=dict(m.labels or {}), version=m.version,
        created_at=_as_utc(m.created_at), updated_at=_as_utc(m.updated_at),
    )


def _probe_result_to_domain(m: models.IsolationProbeResult) -> IsolationProbeResult:
    return IsolationProbeResult(
        id=str(m.id), tenant_id=m.tenant_id, target_name=m.target_name, passed=m.passed,
        breach_count=m.breach_count, sample_size=m.sample_size, details=m.details, checked_at=_as_utc(m.checked_at),
    )


def _entitlement_to_domain(m: models.TenantEntitlement) -> TenantEntitlementRecord:
    return TenantEntitlementRecord(tenant_id=m.tenant_id, module_name=m.module_name, updated_at=_as_utc(m.updated_at))


class SQLAlchemyMultiTenancyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_tenant(self, record: TenantRecord) -> TenantRecord:
        m = models.Tenant(
            id=record.id, name=record.name, status=record.status.value, tier=record.tier,
            organisation_id=record.organisation_id,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _tenant_to_domain(m)

    async def get_tenant(self, tenant_id: str) -> TenantRecord | None:
        m = await self.session.get(models.Tenant, tenant_id)
        return _tenant_to_domain(m) if m else None

    async def update_tenant(self, record: TenantRecord) -> TenantRecord:
        m = await self.session.get(models.Tenant, record.id)
        m.status = record.status.value
        m.tier = record.tier
        m.organisation_id = record.organisation_id
        await self.session.commit()
        await self.session.refresh(m)
        return _tenant_to_domain(m)

    async def list_tenants(
        self, *, status: TenantStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[TenantRecord], int]:
        filters = []
        if status is not None:
            filters.append(models.Tenant.status == status.value)

        count_stmt = select(func.count(models.Tenant.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = select(models.Tenant).where(*filters).order_by(models.Tenant.created_at.desc()).limit(limit).offset(offset)
        rows = await self.session.execute(stmt)
        return [_tenant_to_domain(m) for m in rows.scalars().all()], total

    async def create_probe_result(self, record: IsolationProbeResult) -> IsolationProbeResult:
        m = models.IsolationProbeResult(
            id=record.id, tenant_id=record.tenant_id, target_name=record.target_name, passed=record.passed,
            breach_count=record.breach_count, sample_size=record.sample_size, details=record.details,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _probe_result_to_domain(m)

    async def list_probe_results(
        self, *, tenant_id: str | None = None, target_name: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[IsolationProbeResult], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.IsolationProbeResult.tenant_id == tenant_id)
        if target_name is not None:
            filters.append(models.IsolationProbeResult.target_name == target_name)

        count_stmt = select(func.count(models.IsolationProbeResult.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.IsolationProbeResult).where(*filters)
            .order_by(models.IsolationProbeResult.checked_at.desc()).limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_probe_result_to_domain(m) for m in rows.scalars().all()], total

    async def replace_entitlements(
        self, *, tenant_id: str, module_names: list[str],
    ) -> list[TenantEntitlementRecord]:
        await self.session.execute(
            models.TenantEntitlement.__table__.delete().where(models.TenantEntitlement.tenant_id == tenant_id)
        )
        rows = [models.TenantEntitlement(tenant_id=tenant_id, module_name=name) for name in module_names]
        self.session.add_all(rows)

        tenant = await self.session.get(models.Tenant, tenant_id)
        tenant.entitlements_configured_at = func.now()

        await self.session.commit()
        for row in rows:
            await self.session.refresh(row)
        return [_entitlement_to_domain(m) for m in rows]

    async def list_entitlements(self, tenant_id: str) -> list[TenantEntitlementRecord]:
        stmt = select(models.TenantEntitlement).where(models.TenantEntitlement.tenant_id == tenant_id)
        rows = await self.session.execute(stmt)
        return [_entitlement_to_domain(m) for m in rows.scalars().all()]

    # --- Organisation / Workspace / Environment ---

    async def create_organisation(self, record: OrganisationRecord) -> OrganisationRecord:
        m = models.Organisation(
            id=record.id, name=record.name, status=record.status.value,
            owner_identity_id=record.owner_identity_id, labels=record.labels, version=record.version,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _organisation_to_domain(m)

    async def get_organisation(self, organisation_id: str) -> OrganisationRecord | None:
        m = await self.session.get(models.Organisation, organisation_id)
        return _organisation_to_domain(m) if m else None

    async def update_organisation(self, record: OrganisationRecord) -> OrganisationRecord:
        m = await self.session.get(models.Organisation, record.id)
        m.status = record.status.value
        m.owner_identity_id = record.owner_identity_id
        m.labels = record.labels
        m.version = record.version
        await self.session.commit()
        await self.session.refresh(m)
        return _organisation_to_domain(m)

    async def list_organisations(
        self, *, status: HierarchyStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[OrganisationRecord], int]:
        filters = []
        if status is not None:
            filters.append(models.Organisation.status == status.value)

        count_stmt = select(func.count(models.Organisation.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.Organisation).where(*filters)
            .order_by(models.Organisation.created_at.desc()).limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_organisation_to_domain(m) for m in rows.scalars().all()], total

    async def create_workspace(self, record: WorkspaceRecord) -> WorkspaceRecord:
        m = models.Workspace(
            id=record.id, tenant_id=record.tenant_id, name=record.name, status=record.status.value,
            owner_identity_id=record.owner_identity_id, labels=record.labels, version=record.version,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _workspace_to_domain(m)

    async def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        m = await self.session.get(models.Workspace, workspace_id)
        return _workspace_to_domain(m) if m else None

    async def update_workspace(self, record: WorkspaceRecord) -> WorkspaceRecord:
        m = await self.session.get(models.Workspace, record.id)
        m.status = record.status.value
        m.owner_identity_id = record.owner_identity_id
        m.labels = record.labels
        m.version = record.version
        await self.session.commit()
        await self.session.refresh(m)
        return _workspace_to_domain(m)

    async def list_workspaces(
        self, *, tenant_id: str | None = None, status: HierarchyStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[WorkspaceRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.Workspace.tenant_id == tenant_id)
        if status is not None:
            filters.append(models.Workspace.status == status.value)

        count_stmt = select(func.count(models.Workspace.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.Workspace).where(*filters)
            .order_by(models.Workspace.created_at.desc()).limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_workspace_to_domain(m) for m in rows.scalars().all()], total

    async def create_environment(self, record: EnvironmentRecord) -> EnvironmentRecord:
        m = models.Environment(
            id=record.id, workspace_id=record.workspace_id, name=record.name, kind=record.kind,
            region=record.region, status=record.status.value, owner_identity_id=record.owner_identity_id,
            labels=record.labels, version=record.version,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _environment_to_domain(m)

    async def get_environment(self, environment_id: str) -> EnvironmentRecord | None:
        m = await self.session.get(models.Environment, environment_id)
        return _environment_to_domain(m) if m else None

    async def update_environment(self, record: EnvironmentRecord) -> EnvironmentRecord:
        m = await self.session.get(models.Environment, record.id)
        m.status = record.status.value
        m.owner_identity_id = record.owner_identity_id
        m.labels = record.labels
        m.version = record.version
        await self.session.commit()
        await self.session.refresh(m)
        return _environment_to_domain(m)

    async def list_environments(
        self, *, workspace_id: str | None = None, status: HierarchyStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[EnvironmentRecord], int]:
        filters = []
        if workspace_id is not None:
            filters.append(models.Environment.workspace_id == workspace_id)
        if status is not None:
            filters.append(models.Environment.status == status.value)

        count_stmt = select(func.count(models.Environment.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.Environment).where(*filters)
            .order_by(models.Environment.created_at.desc()).limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_environment_to_domain(m) for m in rows.scalars().all()], total
