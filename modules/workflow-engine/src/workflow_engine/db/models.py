"""SQLAlchemy 2.0 declarative models for the Workflow Engine data model (LLD §3.1).

Entities: WorkflowDefinition, WorkflowInstance, StepExecution, ApprovalRequest,
ReplanEvent. Alembic migrations for these live under ../../alembic/versions.

IDs are Postgres native `uuid` columns but round-trip as plain `str` in
Python (`as_uuid=False`) — the domain layer (core/domain.py) generates and
compares ids as strings throughout, so there's no uuid.UUID<->str conversion
at the repository boundary. SQLite (used for fast local dev/testing without
Postgres) falls back to CHAR(36) via `.with_variant`.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from workflow_engine.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


# JSONB/UUID are Postgres-only types; fall back to generic equivalents so the
# same models work against SQLite in unit tests (in-memory fakes / aiosqlite)
# without a running Postgres instance, per the LLD's unit-test tier requirement.
JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"
    __table_args__ = (
        Index("ix_workflow_definitions_tenant", "tenant_id"),
        Index("ix_workflow_definitions_name_version", "tenant_id", "name", "version", unique=True),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft|published|deprecated
    graph_schema: Mapped[dict] = mapped_column(JSONType)
    tenant_id: Mapped[str] = mapped_column(String(255))
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    instances: Mapped[list[WorkflowInstance]] = relationship(back_populates="definition")


class WorkflowInstance(Base):
    __tablename__ = "workflow_instances"
    __table_args__ = (
        Index("ix_workflow_instances_tenant", "tenant_id"),
        Index("ix_workflow_instances_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    definition_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("workflow_definitions.id"))
    definition_version: Mapped[int]
    status: Mapped[str] = mapped_column(String(32), default="running")
    # running|paused_for_approval|completed|failed|terminated
    current_step_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    context: Mapped[dict] = mapped_column(JSONType, default=dict)
    tenant_id: Mapped[str] = mapped_column(String(255))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trace_id: Mapped[str] = mapped_column(String(64))

    definition: Mapped[WorkflowDefinition] = relationship(back_populates="instances")
    steps: Mapped[list[StepExecution]] = relationship(back_populates="instance")


class StepExecution(Base):
    __tablename__ = "step_executions"
    __table_args__ = (
        Index("ix_step_executions_instance", "instance_id"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    instance_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("workflow_instances.id"))
    step_id: Mapped[str] = mapped_column(String(255))
    execution_mode: Mapped[str] = mapped_column(String(16))  # symbolic|neural|human|auto
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending|running|completed|failed|skipped|replan_triggered
    input_snapshot: Mapped[dict] = mapped_column(JSONType, default=dict)
    output: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    instance: Mapped[WorkflowInstance] = relationship(back_populates="steps")


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    step_execution_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("step_executions.id"))
    human_oversight_ref_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|approved|rejected|timed_out
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReplanEvent(Base):
    __tablename__ = "replan_events"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    instance_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("workflow_instances.id"))
    trigger_reason: Mapped[str] = mapped_column(String(255))
    original_step_id: Mapped[str] = mapped_column(String(255))
    new_graph_delta: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EventOutbox(Base):
    """The transactional outbox (independent architecture assessment
    §3.3): one row per CloudEvents envelope awaiting relay to Kafka,
    written in the same commit as the instance state change it
    accompanies. See `core/domain.py`'s `EventOutboxRecord` docstring
    and `core/outbox_worker.py`."""

    __tablename__ = "event_outbox"
    __table_args__ = (
        Index("ix_event_outbox_status_lease", "status", "lease_expires_at"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True)  # = the CloudEvents envelope's own `id`
    topic: Mapped[str] = mapped_column(String(128))
    tenant_id: Mapped[str] = mapped_column(String(255))
    envelope: Mapped[dict] = mapped_column(JSONType)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|published|failed
    attempts: Mapped[int] = mapped_column(Integer(), default=0)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
