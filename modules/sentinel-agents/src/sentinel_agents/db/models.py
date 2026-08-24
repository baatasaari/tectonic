"""SQLAlchemy 2.0 declarative models for the Sentinel Agents data model
(LLD §3): AgentBaseline, Alert, InterventionRecord, SwarmCorrelationWindow.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, DateTime, Float, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from sentinel_agents.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class AgentBaseline(Base):
    __tablename__ = "agent_baselines"
    __table_args__ = (UniqueConstraint("tenant_id", "agent_ref", "action_type", name="uq_agent_baseline"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    agent_ref: Mapped[str] = mapped_column(String(255))
    action_type: Mapped[str] = mapped_column(String(128))
    mean: Mapped[float] = mapped_column(Float(), default=0.0)
    m2: Mapped[float] = mapped_column(Float(), default=0.0)
    sample_count: Mapped[int] = mapped_column(Integer(), default=0)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    alert_type: Mapped[str] = mapped_column(String(16))
    agent_refs: Mapped[list[str]] = mapped_column(JSONType, default=list)
    severity: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(32), default="detected")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InterventionRecordModel(Base):
    __tablename__ = "intervention_records"
    __table_args__ = (Index("ix_intervention_records_alert", "alert_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    alert_id: Mapped[str] = mapped_column(UUIDType)
    intervention_type: Mapped[str] = mapped_column(String(16))
    target_ref: Mapped[str] = mapped_column(String(255), default="")
    outcome: Mapped[str] = mapped_column(String(64), default="")
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SwarmCorrelationWindowModel(Base):
    __tablename__ = "swarm_correlation_windows"
    __table_args__ = (Index("ix_swarm_windows_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    agent_refs_involved: Mapped[list[str]] = mapped_column(JSONType, default=list)
    correlation_score: Mapped[float] = mapped_column(Float(), default=0.0)
    pattern_description: Mapped[str] = mapped_column(String(1024), default="")
