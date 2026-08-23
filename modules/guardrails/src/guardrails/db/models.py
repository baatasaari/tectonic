"""SQLAlchemy 2.0 declarative models for the Guardrails data model
(LLD §3): PolicyProfile, InterventionLog, RedTeamRun, BypassIncident.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, Boolean, Float, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from guardrails.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class PolicyProfile(Base):
    __tablename__ = "policy_profiles"
    __table_args__ = (Index("ix_policy_profiles_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    enabled_checks: Mapped[list[str]] = mapped_column(JSONType, default=list)
    pii_entity_types: Mapped[list[str]] = mapped_column(JSONType, default=list)
    denied_topics: Mapped[list[str]] = mapped_column(JSONType, default=list)
    groundedness_threshold: Mapped[float] = mapped_column(Float(), default=0.85)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class InterventionLog(Base):
    __tablename__ = "intervention_logs"
    __table_args__ = (Index("ix_intervention_logs_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    policy_profile_id: Mapped[str] = mapped_column(UUIDType)
    stage: Mapped[str] = mapped_column(String(16))
    check_type: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(16))
    violation_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float(), default=0.0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RedTeamRun(Base):
    __tablename__ = "red_team_runs"
    __table_args__ = (Index("ix_red_team_runs_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    attempts_generated: Mapped[int] = mapped_column(Integer(), default=0)
    successful_bypasses: Mapped[int] = mapped_column(Integer(), default=0)
    run_at: Mapped[datetime] = mapped_column(server_default=func.now())


class BypassIncident(Base):
    __tablename__ = "bypass_incidents"
    __table_args__ = (Index("ix_bypass_incidents_run", "red_team_run_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    red_team_run_id: Mapped[str] = mapped_column(UUIDType)
    attack_pattern: Mapped[str] = mapped_column(String(1024))
    target_check: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16), default="high")
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
