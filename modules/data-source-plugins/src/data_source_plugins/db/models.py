"""SQLAlchemy 2.0 declarative models for the Data Source Plugins data
model (LLD §3): ConnectorConfig, SchemaSnapshot, SyncRun, QualityScore,
DriftIncident.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, Boolean, DateTime, Float, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from data_source_plugins.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class ConnectorConfig(Base):
    __tablename__ = "connector_configs"
    __table_args__ = (Index("ix_connector_configs_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(64))
    connection_config: Mapped[dict] = mapped_column(JSONType, default=dict)
    secrets_ref: Mapped[str] = mapped_column(String(255), default="")
    sync_schedule: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SchemaSnapshot(Base):
    __tablename__ = "schema_snapshots"
    __table_args__ = (Index("ix_schema_snapshots_connector", "connector_id", "version"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    connector_id: Mapped[str] = mapped_column(UUIDType)
    schema_json: Mapped[dict] = mapped_column("schema", JSONType, default=dict)
    version: Mapped[int] = mapped_column(Integer())
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = (Index("ix_sync_runs_connector", "connector_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    connector_id: Mapped[str] = mapped_column(UUIDType)
    status: Mapped[str] = mapped_column(String(32), default="running")
    records_synced: Mapped[int] = mapped_column(Integer(), default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QualityScore(Base):
    __tablename__ = "quality_scores"
    __table_args__ = (Index("ix_quality_scores_connector", "connector_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    connector_id: Mapped[str] = mapped_column(UUIDType)
    sync_run_id: Mapped[str] = mapped_column(UUIDType)
    completeness_score: Mapped[float] = mapped_column(Float())
    freshness_score: Mapped[float] = mapped_column(Float())
    format_validity_score: Mapped[float] = mapped_column(Float())
    overall_score: Mapped[float] = mapped_column(Float())
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DriftIncident(Base):
    __tablename__ = "drift_incidents"
    __table_args__ = (Index("ix_drift_incidents_connector", "connector_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    connector_id: Mapped[str] = mapped_column(UUIDType)
    schema_diff: Mapped[dict] = mapped_column(JSONType, default=dict)
    classification: Mapped[str] = mapped_column(String(32), default="additive")
    auto_adapted: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
