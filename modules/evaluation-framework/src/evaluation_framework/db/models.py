"""SQLAlchemy 2.0 declarative models for the Evaluation Framework data
model (LLD §3): EvalRun, MetricScore, GateResult, DomainMetricPack.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, Boolean, DateTime, Float, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from evaluation_framework.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class EvalRun(Base):
    __tablename__ = "eval_runs"
    __table_args__ = (
        Index("ix_eval_runs_tenant", "tenant_id"),
        Index("ix_eval_runs_tenant_agent", "tenant_id", "agent_ref"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    trigger_source: Mapped[str] = mapped_column(String(32))
    agent_ref: Mapped[str] = mapped_column(String(255))
    metrics_evaluated: Mapped[list[str]] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(24), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MetricScore(Base):
    __tablename__ = "metric_scores"
    __table_args__ = (
        Index("ix_metric_scores_run", "eval_run_id"),
        Index("ix_metric_scores_tenant_agent", "tenant_id", "agent_ref"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    eval_run_id: Mapped[str] = mapped_column(UUIDType)
    tenant_id: Mapped[str] = mapped_column(String(255))
    agent_ref: Mapped[str] = mapped_column(String(255))
    metric_name: Mapped[str] = mapped_column(String(64))
    score: Mapped[float] = mapped_column(Float())
    threshold: Mapped[float] = mapped_column(Float())
    passed: Mapped[bool] = mapped_column(Boolean())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GateResult(Base):
    __tablename__ = "gate_results"
    __table_args__ = (Index("ix_gate_results_run", "eval_run_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    eval_run_id: Mapped[str] = mapped_column(UUIDType)
    overall_passed: Mapped[bool] = mapped_column(Boolean())
    blocking_failures: Mapped[list[str]] = mapped_column(JSONType, default=list)
    environment: Mapped[str] = mapped_column(String(32), default="production")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DomainMetricPack(Base):
    __tablename__ = "domain_metric_packs"
    __table_args__ = (Index("ix_domain_metric_packs_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    pack_name: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean(), default=True)
    custom_thresholds: Mapped[dict] = mapped_column(JSONType, default=dict)
