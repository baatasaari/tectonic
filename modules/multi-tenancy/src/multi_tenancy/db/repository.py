"""SQLAlchemy-backed implementation of MultiTenancyRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from multi_tenancy.core.domain import (
    EnvironmentRecord,
    EventOutboxRecord,
    HierarchyStatus,
    IsolationProbeResult,
    OptimisticConcurrencyError,
    OrganisationRecord,
    OutboxEventStatus,
    QuotaSet,
    ResidencyPolicy,
    ResourceAllocation,
    ResourceAllocationStatus,
    TenantEntitlementRecord,
    TenantRecord,
    TenantStatus,
    WorkspaceRecord,
    now,
    quota_window_start,
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


def _quota_set_to_domain(m: models.TenantQuotaSet) -> QuotaSet:
    return QuotaSet(
        tenant_id=str(m.tenant_id), limits=dict(m.limits or {}), configured_at=_as_utc(m.configured_at),
        version=m.version, updated_at=_as_utc(m.updated_at),
    )


def _residency_policy_to_domain(m: models.TenantResidencyPolicy) -> ResidencyPolicy:
    return ResidencyPolicy(
        tenant_id=str(m.tenant_id), allowed_regions=list(m.allowed_regions or []),
        configured_at=_as_utc(m.configured_at), version=m.version, updated_at=_as_utc(m.updated_at),
    )


def _outbox_to_domain(m: models.EventOutbox) -> EventOutboxRecord:
    return EventOutboxRecord(
        id=str(m.id), topic=m.topic, tenant_id=m.tenant_id, envelope=dict(m.envelope or {}),
        status=OutboxEventStatus(m.status), attempts=m.attempts, worker_id=m.worker_id,
        lease_expires_at=_as_utc(m.lease_expires_at), last_error=m.last_error,
        created_at=_as_utc(m.created_at), published_at=_as_utc(m.published_at),
    )


def _resource_allocation_to_domain(m: models.ResourceAllocation) -> ResourceAllocation:
    return ResourceAllocation(
        id=str(m.id), environment_id=str(m.environment_id), resources=dict(m.resources or {}),
        reserved_capacity=m.reserved_capacity, status=ResourceAllocationStatus(m.status),
        requested_by=m.requested_by, approved_by=m.approved_by, rejection_reason=m.rejection_reason,
        version=m.version, created_at=_as_utc(m.created_at), updated_at=_as_utc(m.updated_at),
    )


class SQLAlchemyMultiTenancyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _compare_and_swap(self, model, record_id: str, *, expected_version: int, values: dict) -> None:
        """Real optimistic-concurrency compare-and-swap: a real `UPDATE
        ... WHERE id = :id AND version = :expected_version`, never the
        unconditional `m.version = record.version` overwrite this used
        to do (which silently let the last of two concurrent writers
        win with no conflict raised at all). Zero affected rows means
        someone else's update already moved the row's version past what
        this caller last saw -- see `core/domain.py`'s
        `OptimisticConcurrencyError`. Shared by every versioned record
        type (Organisation/Workspace/Environment/ResourceAllocation)
        rather than reimplemented per type."""
        stmt = (
            sa_update(model)
            .where(model.id == record_id, model.version == expected_version)
            .values(version=expected_version + 1, **values)
        )
        result = await self.session.execute(stmt)
        if result.rowcount == 0:
            await self.session.rollback()
            raise OptimisticConcurrencyError(expected_version=expected_version)
        await self.session.commit()

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

    def _add_outbox_row(self, *, topic: str, envelope: dict[str, Any]) -> None:
        self.session.add(
            models.EventOutbox(id=envelope["id"], topic=topic, tenant_id=envelope["tenant_id"], envelope=envelope)
        )

    async def create_tenant_and_enqueue_event(
        self, record: TenantRecord, *, topic: str, envelope: dict[str, Any],
    ) -> TenantRecord:
        m = models.Tenant(
            id=record.id, name=record.name, status=record.status.value, tier=record.tier,
            organisation_id=record.organisation_id,
        )
        self.session.add(m)
        self._add_outbox_row(topic=topic, envelope=envelope)

        # One commit for both writes -- the whole point of the outbox pattern: if this
        # transaction commits, the tenant row and its accompanying event are guaranteed
        # to both be there; if it rolls back, neither is.
        await self.session.commit()
        await self.session.refresh(m)
        return _tenant_to_domain(m)

    async def update_tenant_and_enqueue_event(
        self, record: TenantRecord, *, topic: str, envelope: dict[str, Any],
    ) -> TenantRecord:
        m = await self.session.get(models.Tenant, record.id)
        m.status = record.status.value
        m.tier = record.tier
        m.organisation_id = record.organisation_id
        self._add_outbox_row(topic=topic, envelope=envelope)

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

    async def update_organisation(self, record: OrganisationRecord, *, expected_version: int) -> OrganisationRecord:
        await self._compare_and_swap(
            models.Organisation, record.id, expected_version=expected_version,
            values={
                "status": record.status.value, "owner_identity_id": record.owner_identity_id,
                "labels": record.labels,
            },
        )
        m = await self.session.get(models.Organisation, record.id)
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

    async def update_workspace(self, record: WorkspaceRecord, *, expected_version: int) -> WorkspaceRecord:
        await self._compare_and_swap(
            models.Workspace, record.id, expected_version=expected_version,
            values={
                "status": record.status.value, "owner_identity_id": record.owner_identity_id,
                "labels": record.labels,
            },
        )
        m = await self.session.get(models.Workspace, record.id)
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

    async def update_environment(self, record: EnvironmentRecord, *, expected_version: int) -> EnvironmentRecord:
        await self._compare_and_swap(
            models.Environment, record.id, expected_version=expected_version,
            values={
                "status": record.status.value, "owner_identity_id": record.owner_identity_id,
                "labels": record.labels,
            },
        )
        m = await self.session.get(models.Environment, record.id)
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

    # --- Quota Set / real-time quota enforcement ---

    async def get_quota_set(self, tenant_id: str) -> QuotaSet | None:
        m = await self.session.get(models.TenantQuotaSet, tenant_id)
        return _quota_set_to_domain(m) if m else None

    async def upsert_quota_set(self, *, tenant_id: str, limits: dict[str, float]) -> QuotaSet:
        m = await self.session.get(models.TenantQuotaSet, tenant_id)
        if m is None:
            m = models.TenantQuotaSet(tenant_id=tenant_id, limits=limits, configured_at=func.now(), version=1)
            self.session.add(m)
        else:
            m.limits = limits
            m.configured_at = func.now()
            m.version += 1
        await self.session.commit()
        await self.session.refresh(m)
        return _quota_set_to_domain(m)

    async def get_residency_policy(self, tenant_id: str) -> ResidencyPolicy | None:
        m = await self.session.get(models.TenantResidencyPolicy, tenant_id)
        return _residency_policy_to_domain(m) if m else None

    async def upsert_residency_policy(self, *, tenant_id: str, allowed_regions: list[str]) -> ResidencyPolicy:
        m = await self.session.get(models.TenantResidencyPolicy, tenant_id)
        if m is None:
            m = models.TenantResidencyPolicy(
                tenant_id=tenant_id, allowed_regions=allowed_regions, configured_at=func.now(), version=1,
            )
            self.session.add(m)
        else:
            m.allowed_regions = allowed_regions
            m.configured_at = func.now()
            m.version += 1
        await self.session.commit()
        await self.session.refresh(m)
        return _residency_policy_to_domain(m)

    async def increment_quota_counter(
        self, *, tenant_id: str, resource_class: str, amount: float, window_seconds: int, now: datetime,
    ) -> float:
        # A real atomic upsert -- INSERT ... ON CONFLICT DO UPDATE SET count = count +
        # amount, RETURNING the new total in the same statement -- so concurrent callers
        # never race a read-then-write increment; each request's own increment always
        # lands, whichever order they commit in.
        window_start = quota_window_start(now, window_seconds)
        stmt = (
            pg_insert(models.QuotaCounter)
            .values(tenant_id=tenant_id, resource_class=resource_class, window_start=window_start, count=amount)
            .on_conflict_do_update(
                index_elements=[
                    models.QuotaCounter.tenant_id, models.QuotaCounter.resource_class,
                    models.QuotaCounter.window_start,
                ],
                set_={"count": models.QuotaCounter.count + amount},
            )
            .returning(models.QuotaCounter.count)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return float(result.scalar_one())

    # --- Resource Allocation ---

    async def create_resource_allocation(self, record: ResourceAllocation) -> ResourceAllocation:
        m = models.ResourceAllocation(
            id=record.id, environment_id=record.environment_id, resources=record.resources,
            reserved_capacity=record.reserved_capacity, status=record.status.value,
            requested_by=record.requested_by, approved_by=record.approved_by,
            rejection_reason=record.rejection_reason, version=record.version,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _resource_allocation_to_domain(m)

    async def get_resource_allocation(self, allocation_id: str) -> ResourceAllocation | None:
        m = await self.session.get(models.ResourceAllocation, allocation_id)
        return _resource_allocation_to_domain(m) if m else None

    async def update_resource_allocation(
        self, record: ResourceAllocation, *, expected_version: int,
    ) -> ResourceAllocation:
        await self._compare_and_swap(
            models.ResourceAllocation, record.id, expected_version=expected_version,
            values={
                "resources": record.resources, "status": record.status.value,
                "approved_by": record.approved_by, "rejection_reason": record.rejection_reason,
            },
        )
        m = await self.session.get(models.ResourceAllocation, record.id)
        return _resource_allocation_to_domain(m)

    async def get_active_resource_allocation(self, environment_id: str) -> ResourceAllocation | None:
        stmt = (
            select(models.ResourceAllocation)
            .where(
                models.ResourceAllocation.environment_id == environment_id,
                models.ResourceAllocation.status == ResourceAllocationStatus.ACTIVE.value,
            )
            .order_by(models.ResourceAllocation.updated_at.desc())
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalars().first()
        return _resource_allocation_to_domain(row) if row else None

    async def list_resource_allocations(
        self, *, environment_id: str | None = None, status: ResourceAllocationStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[ResourceAllocation], int]:
        filters = []
        if environment_id is not None:
            filters.append(models.ResourceAllocation.environment_id == environment_id)
        if status is not None:
            filters.append(models.ResourceAllocation.status == status.value)

        count_stmt = select(func.count(models.ResourceAllocation.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.ResourceAllocation).where(*filters)
            .order_by(models.ResourceAllocation.created_at.desc()).limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_resource_allocation_to_domain(m) for m in rows.scalars().all()], total

    # --- Event outbox relay (core/outbox_worker.py) ---

    async def claim_next_outbox_event(self, worker_id: str, lease_seconds: int) -> EventOutboxRecord | None:
        """`SELECT ... FOR UPDATE SKIP LOCKED`: the row-level lock this
        takes is what lets multiple worker processes/pods poll
        concurrently without two of them ever claiming the same pending
        event -- a competing claimant simply skips a row another
        transaction already has locked, rather than blocking on it or
        double-claiming it. Same shape Workflow Engine's own
        `claim_next_outbox_event` already established."""
        moment = now()
        stmt = (
            select(models.EventOutbox)
            .where(
                models.EventOutbox.status == OutboxEventStatus.PENDING.value,
                (models.EventOutbox.lease_expires_at.is_(None)) | (models.EventOutbox.lease_expires_at < moment),
            )
            .order_by(models.EventOutbox.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        rows = await self.session.execute(stmt)
        m = rows.scalars().first()
        if m is None:
            return None
        m.worker_id = worker_id
        m.attempts += 1
        m.lease_expires_at = moment + timedelta(seconds=lease_seconds)
        await self.session.commit()
        await self.session.refresh(m)
        return _outbox_to_domain(m)

    async def mark_outbox_event_published(self, event_id: str) -> None:
        m = await self.session.get(models.EventOutbox, event_id)
        if m is None:
            return
        m.status = OutboxEventStatus.PUBLISHED.value
        m.published_at = now()
        m.lease_expires_at = None
        await self.session.commit()

    async def requeue_outbox_event_for_retry(self, event_id: str, *, error: str) -> None:
        m = await self.session.get(models.EventOutbox, event_id)
        if m is None:
            return
        m.lease_expires_at = None
        m.last_error = error[:1024]
        await self.session.commit()

    async def fail_exhausted_outbox_events(self, max_attempts: int) -> int:
        result = await self.session.execute(
            sa_update(models.EventOutbox)
            .where(
                models.EventOutbox.status == OutboxEventStatus.PENDING.value,
                models.EventOutbox.attempts >= max_attempts,
            )
            .values(status=OutboxEventStatus.FAILED.value, last_error=f"exceeded max attempts ({max_attempts})")
        )
        await self.session.commit()
        return result.rowcount or 0

    async def force_expire_stale_outbox_leases(self) -> int:
        moment = now()
        result = await self.session.execute(
            sa_update(models.EventOutbox)
            .where(
                models.EventOutbox.status == OutboxEventStatus.PENDING.value,
                models.EventOutbox.lease_expires_at.is_not(None),
                models.EventOutbox.lease_expires_at > moment,
            )
            .values(lease_expires_at=moment)
        )
        await self.session.commit()
        return result.rowcount or 0
