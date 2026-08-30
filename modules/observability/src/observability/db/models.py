"""SQLAlchemy 2.0 declarative model for the Observability data model
(LLD §3): follows OpenTelemetry's span shape plus platform extension
attributes, plus this module's own SLO/alerting surfaces (Phase 1
kernel) -- real tables this module owns, not part of the LLD's
upstream span shape.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, Boolean, DateTime, Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from observability.db.base import Base

JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


def _new_id() -> str:
    return str(uuid.uuid4())


class Span(Base):
    __tablename__ = "spans"
    __table_args__ = (
        Index("ix_spans_tenant_trace", "tenant_id", "trace_id"),
        Index("ix_spans_tenant_workflow_type", "tenant_id", "workflow_type"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255))
    trace_id: Mapped[str] = mapped_column(String(64))
    span_id: Mapped[str] = mapped_column(String(64))
    parent_span_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    service_name: Mapped[str] = mapped_column(String(64))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attributes: Mapped[dict] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    workflow_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SLO(Base):
    __tablename__ = "slos"
    __table_args__ = (Index("ix_slos_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    metric: Mapped[str] = mapped_column(String(32))
    target: Mapped[float] = mapped_column(Float())
    window_hours: Mapped[int] = mapped_column(Integer())
    service_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AlertRule(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (Index("ix_alert_rules_tenant_enabled", "tenant_id", "enabled"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    metric: Mapped[str] = mapped_column(String(32))
    comparison: Mapped[str] = mapped_column(String(8))
    threshold: Mapped[float] = mapped_column(Float())
    window_hours: Mapped[int] = mapped_column(Integer())
    service_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean(), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AlertEvent(Base):
    __tablename__ = "alert_events"
    __table_args__ = (
        Index("ix_alert_events_rule", "rule_id"),
        Index("ix_alert_events_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    rule_id: Mapped[str] = mapped_column(String(255))
    tenant_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16))
    value: Mapped[float] = mapped_column(Float())
    threshold: Mapped[float] = mapped_column(Float())
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
