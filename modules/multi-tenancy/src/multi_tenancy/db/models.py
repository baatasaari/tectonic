"""SQLAlchemy 2.0 declarative models for the Multi-tenancy module data
model (LLD §3): Tenant, IsolationProbeResult, and the platform hierarchy
control plane (Organisation, Workspace, Environment).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from multi_tenancy.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


UUIDType = PG_UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")
JSONType = JSONB().with_variant(JSON(), "sqlite")


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="active")
    tier: Mapped[str] = mapped_column(String(32), default="standard")
    organisation_id: Mapped[str | None] = mapped_column(
        UUIDType, ForeignKey("organisations.id"), nullable=True,
    )
    entitlements_configured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class Organisation(Base):
    """Top of the platform hierarchy control plane (LLD §Level 3 "The
    platform hierarchy control plane"): `Organisation -> Tenant ->
    Workspace -> Environment`. See `core/domain.py`'s `OrganisationRecord`
    docstring."""

    __tablename__ = "organisations"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="active")
    owner_identity_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    labels: Mapped[dict] = mapped_column(JSONType, default=dict)
    version: Mapped[int] = mapped_column(Integer(), default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class Workspace(Base):
    """Second level of the platform hierarchy -- always scoped to exactly
    one tenant. See `core/domain.py`'s `WorkspaceRecord` docstring."""

    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="active")
    owner_identity_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    labels: Mapped[dict] = mapped_column(JSONType, default=dict)
    version: Mapped[int] = mapped_column(Integer(), default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class Environment(Base):
    """Third level of the platform hierarchy -- always scoped to exactly
    one workspace. See `core/domain.py`'s `EnvironmentRecord` docstring."""

    __tablename__ = "environments"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    workspace_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("workspaces.id"))
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(32), default="development")
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    owner_identity_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    labels: Mapped[dict] = mapped_column(JSONType, default=dict)
    version: Mapped[int] = mapped_column(Integer(), default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class IsolationProbeResult(Base):
    __tablename__ = "isolation_probe_results"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    target_name: Mapped[str] = mapped_column(String(255))
    passed: Mapped[bool] = mapped_column(Boolean())
    breach_count: Mapped[int] = mapped_column(Integer(), default=0)
    sample_size: Mapped[int] = mapped_column(Integer(), default=0)
    details: Mapped[str] = mapped_column(Text())
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TenantQuotaSet(Base):
    """One row per tenant: the whole resource-class `limits` dict,
    always replaced wholesale. See `core/domain.py`'s `QuotaSet`
    docstring."""

    __tablename__ = "tenant_quota_sets"

    tenant_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("tenants.id"), primary_key=True)
    limits: Mapped[dict] = mapped_column(JSONType, default=dict)
    configured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer(), default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class TenantResidencyPolicy(Base):
    """One row per tenant: the whole `allowed_regions` list, always
    replaced wholesale. See `core/domain.py`'s `ResidencyPolicy`
    docstring."""

    __tablename__ = "tenant_residency_policies"

    tenant_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("tenants.id"), primary_key=True)
    allowed_regions: Mapped[list] = mapped_column(JSONType, default=list)
    configured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer(), default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class QuotaCounter(Base):
    """A real fixed-window rate counter: one row per (tenant,
    resource_class, window_start), atomically upserted by
    `SQLAlchemyMultiTenancyRepository.increment_quota_counter`. A new
    window is a new row -- no explicit reset needed for correctness,
    though old rows accumulate; a real cleanup/TTL job for stale windows
    is separate, unbuilt work (see this module's README)."""

    __tablename__ = "quota_counters"

    tenant_id: Mapped[str] = mapped_column(UUIDType, primary_key=True)
    resource_class: Mapped[str] = mapped_column(String(128), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[float] = mapped_column(Float(), default=0.0)


class ResourceAllocation(Base):
    """One environment's approved/requested capacity across every
    resource dimension (`resources`, a flexible dict -- see
    `core/domain.py`'s `ResourceAllocation` docstring), plus its
    request -> approve/reject lifecycle."""

    __tablename__ = "resource_allocations"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    environment_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("environments.id"))
    resources: Mapped[dict] = mapped_column(JSONType, default=dict)
    reserved_capacity: Mapped[bool] = mapped_column(Boolean(), default=False)
    status: Mapped[str] = mapped_column(String(16), default="requested")
    requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    version: Mapped[int] = mapped_column(Integer(), default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class EventOutbox(Base):
    """The transactional outbox (independent architecture assessment
    §3.3): one row per CloudEvents envelope awaiting relay to Kafka,
    written in the same commit as the Tenant state change it
    accompanies. The rollout of Workflow Engine's own `EventOutbox`
    model (Module 1) to a second module. See `core/domain.py`'s
    `EventOutboxRecord` docstring and `core/outbox_worker.py`."""

    __tablename__ = "event_outbox"
    __table_args__ = (
        Index("ix_event_outbox_status_lease", "status", "lease_expires_at"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True)  # = the CloudEvents envelope's own `id`
    topic: Mapped[str] = mapped_column(String(128))
    tenant_id: Mapped[str] = mapped_column(String(255))
    envelope: Mapped[dict] = mapped_column(JSONType)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempts: Mapped[int] = mapped_column(Integer(), default=0)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TenantEntitlement(Base):
    """The platform's feature-flag store: one row per (tenant, module)
    the tenant's subscription currently includes. See
    `core/domain.py`'s `TenantEntitlementRecord` docstring for why
    writes are always a wholesale replace."""

    __tablename__ = "tenant_entitlements"

    tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    module_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
