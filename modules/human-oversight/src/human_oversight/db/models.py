"""SQLAlchemy 2.0 declarative models for the Human Oversight data model
(LLD §3): OversightRequest, Decision, OverrideRecord, NotificationLog.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from human_oversight.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class OversightRequest(Base):
    __tablename__ = "oversight_requests"
    __table_args__ = (
        Index("ix_oversight_requests_tenant", "tenant_id"),
        Index("ix_oversight_requests_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    requesting_module: Mapped[str] = mapped_column(String(128))
    requesting_ref: Mapped[str] = mapped_column(String(255))
    context: Mapped[dict] = mapped_column(JSONType, default=dict)
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    claimed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (Index("ix_decisions_request", "request_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    request_id: Mapped[str] = mapped_column(UUIDType)
    decision: Mapped[str] = mapped_column(String(16))
    decided_by: Mapped[str] = mapped_column(String(255))
    decision_reason: Mapped[str] = mapped_column(String(2048), default="")
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OverrideRecordModel(Base):
    __tablename__ = "override_records"
    __table_args__ = (Index("ix_override_records_decision", "decision_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    decision_id: Mapped[str] = mapped_column(UUIDType)
    original_agent_proposal: Mapped[dict] = mapped_column(JSONType, default=dict)
    human_override_action: Mapped[dict] = mapped_column(JSONType, default=dict)
    override_reason: Mapped[str] = mapped_column(String(2048), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationLog(Base):
    __tablename__ = "notification_logs"
    __table_args__ = (Index("ix_notification_logs_request", "request_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    request_id: Mapped[str] = mapped_column(UUIDType)
    channel: Mapped[str] = mapped_column(String(32))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(16), default="pending")
