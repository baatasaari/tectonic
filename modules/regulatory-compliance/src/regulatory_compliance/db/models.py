"""SQLAlchemy 2.0 declarative models for the Regulatory and Compliance
data model (LLD §3): FrameworkProfile, ControlMapping,
ControlImplementationEvent, EvidencePack.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, Boolean, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from regulatory_compliance.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class FrameworkProfile(Base):
    __tablename__ = "framework_profiles"
    __table_args__ = (Index("ix_framework_profiles_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    framework_name: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ControlMapping(Base):
    __tablename__ = "control_mappings"
    __table_args__ = (Index("ix_control_mappings_control_framework", "control_name", "framework_name"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    control_name: Mapped[str] = mapped_column(String(128))
    framework_name: Mapped[str] = mapped_column(String(64))
    framework_version: Mapped[str] = mapped_column(String(32))
    clause_references: Mapped[list[str]] = mapped_column(JSONType, default=list)
    mapping_rationale: Mapped[str] = mapped_column(Text())
    deprecated: Mapped[bool] = mapped_column(Boolean, default=False)


class ControlImplementationEvent(Base):
    __tablename__ = "control_implementation_events"
    __table_args__ = (Index("ix_control_events_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    control_name: Mapped[str] = mapped_column(String(128))
    source_module: Mapped[str] = mapped_column(String(64))
    evidence_ref: Mapped[str] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())


class EvidencePack(Base):
    __tablename__ = "evidence_packs"
    __table_args__ = (
        Index("ix_evidence_packs_tenant", "tenant_id"),
        # Serves the durable-worker claim query's WHERE status = 'generating' AND
        # (lease_expires_at IS NULL OR lease_expires_at < now()) ORDER BY created_at.
        Index("ix_evidence_packs_status_lease", "status", "lease_expires_at"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    framework_name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="requested")
    generated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    coverage_percentage: Mapped[float] = mapped_column(Float(), default=0.0)
    document_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_format: Mapped[str] = mapped_column(String(8), default="pdf")
    document_bytes_b64: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # Durable job-queue fields — see core/evidence_worker.py.
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer(), default=0)
    last_error: Mapped[str | None] = mapped_column(Text(), nullable=True)
