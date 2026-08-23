"""SQLAlchemy 2.0 declarative model for the Observability data model
(LLD §3): follows OpenTelemetry's span shape plus platform extension
attributes — this module defines no custom schema beyond that.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from observability.db.base import Base

JSONType = JSONB().with_variant(JSON(), "sqlite")


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
    start_time: Mapped[datetime]
    end_time: Mapped[datetime]
    attributes: Mapped[dict] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    workflow_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ingested_at: Mapped[datetime]
