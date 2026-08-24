"""SQLAlchemy 2.0 declarative models for the Auditability data model (LLD
§3): AuditEvent, AuditPack.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    JSON,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from auditability.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        # Enforces the chain's own invariant at the DB level too, not just via the
        # per-tenant SELECT ... FOR UPDATE lock in the repository: two rows for the
        # same tenant can never share a sequence_number.
        UniqueConstraint("tenant_id", "sequence_number", name="uq_audit_events_tenant_sequence"),
        Index("ix_audit_events_tenant_sequence", "tenant_id", "sequence_number"),
        Index("ix_audit_events_tenant_event_type", "tenant_id", "event_type"),
        Index("ix_audit_events_tenant_source_module", "tenant_id", "source_module"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    source_module: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)
    sequence_number: Mapped[int] = mapped_column(Integer())
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_hash: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditPack(Base):
    __tablename__ = "audit_packs"
    __table_args__ = (
        Index("ix_audit_packs_tenant", "tenant_id"),
        # Serves the durable-worker claim query's WHERE status = 'generating' AND
        # (lease_expires_at IS NULL OR lease_expires_at < now()) ORDER BY created_at.
        Index("ix_audit_packs_status_lease", "status", "lease_expires_at"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="requested")
    filter_event_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    filter_source_module: Mapped[str | None] = mapped_column(String(64), nullable=True)
    filter_control_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    filter_occurred_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    filter_occurred_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_count: Mapped[int] = mapped_column(Integer(), default=0)
    chain_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_format: Mapped[str] = mapped_column(String(8), default="pdf")
    document_bytes_b64: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Durable job-queue fields — see core/audit_pack_worker.py.
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer(), default=0)
    last_error: Mapped[str | None] = mapped_column(Text(), nullable=True)
