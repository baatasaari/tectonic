"""SQLAlchemy 2.0 declarative models for the Tool Orchestration data model
(LLD §3.1): ToolDefinition, ToolInvocation, ReliabilityScore.
CircuitBreakerState is Redis-only (hot, ephemeral) — not persisted here,
matching the LLD's stack table ("Circuit breaker state | Redis").
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, Boolean, DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from tool_orchestration.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class ToolDefinition(Base):
    __tablename__ = "tool_definitions"
    __table_args__ = (Index("ix_tool_definitions_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    mcp_server_ref: Mapped[str] = mapped_column(String(255))
    schema_: Mapped[dict] = mapped_column("schema", JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="active")
    synthesised: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ToolInvocation(Base):
    __tablename__ = "tool_invocations"
    __table_args__ = (Index("ix_tool_invocations_tool", "tool_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tool_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("tool_definitions.id"))
    agent_ref: Mapped[str] = mapped_column(String(255))
    workflow_instance_id: Mapped[str | None] = mapped_column(UUIDType, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    retry_count: Mapped[int] = mapped_column(default=0)
    latency_ms: Mapped[float] = mapped_column(Float(), default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReliabilityScore(Base):
    __tablename__ = "reliability_scores"

    tool_id: Mapped[str] = mapped_column(UUIDType, primary_key=True)
    rolling_success_rate: Mapped[float] = mapped_column(Float(), default=1.0)
    rolling_avg_latency_ms: Mapped[float] = mapped_column(Float(), default=0.0)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
