"""SQLAlchemy-backed implementation of MultiTenancyRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from multi_tenancy.core.domain import IsolationProbeResult, TenantRecord, TenantStatus
from multi_tenancy.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _tenant_to_domain(m: models.Tenant) -> TenantRecord:
    return TenantRecord(
        id=str(m.id), name=m.name, status=TenantStatus(m.status), tier=m.tier,
        created_at=_as_utc(m.created_at), updated_at=_as_utc(m.updated_at),
    )


def _probe_result_to_domain(m: models.IsolationProbeResult) -> IsolationProbeResult:
    return IsolationProbeResult(
        id=str(m.id), tenant_id=m.tenant_id, target_name=m.target_name, passed=m.passed,
        breach_count=m.breach_count, sample_size=m.sample_size, details=m.details, checked_at=_as_utc(m.checked_at),
    )


class SQLAlchemyMultiTenancyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_tenant(self, record: TenantRecord) -> TenantRecord:
        m = models.Tenant(id=record.id, name=record.name, status=record.status.value, tier=record.tier)
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
