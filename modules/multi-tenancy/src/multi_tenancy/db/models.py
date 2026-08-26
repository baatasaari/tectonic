"""SQLAlchemy 2.0 declarative models for the Multi-tenancy module data
model (LLD §3): Tenant, IsolationProbeResult.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from multi_tenancy.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="active")
    tier: Mapped[str] = mapped_column(String(32), default="standard")
    entitlements_configured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
