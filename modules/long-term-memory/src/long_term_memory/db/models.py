"""SQLAlchemy 2.0 declarative models for the Long-Term Memory data model
(LLD §3.1): MemoryItem, ConsolidationRun, ReflectionEntry, DeletionRecord.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, Boolean, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from long_term_memory.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class MemoryItem(Base):
    __tablename__ = "memory_items"
    __table_args__ = (
        Index("ix_memory_items_tenant_scope", "tenant_id", "scope"),
        Index("ix_memory_items_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    scope: Mapped[str] = mapped_column(String(255))
    memory_type: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text())
    visibility_policy_ref: Mapped[str] = mapped_column(String(255), default="")
    vector_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    graph_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    relevance_score: Mapped[float] = mapped_column(Float(), default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConsolidationRun(Base):
    __tablename__ = "consolidation_runs"
    __table_args__ = (Index("ix_consolidation_runs_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    items_merged_count: Mapped[int] = mapped_column(Integer(), default=0)
    items_decayed_count: Mapped[int] = mapped_column(Integer(), default=0)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReflectionEntry(Base):
    __tablename__ = "reflection_entries"
    __table_args__ = (Index("ix_reflection_entries_tenant_agent", "tenant_id", "agent_ref"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    agent_ref: Mapped[str] = mapped_column(String(255))
    triggering_interaction_ref: Mapped[str] = mapped_column(String(255))
    reflection_content: Mapped[str] = mapped_column(Text())
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeletionRecordModel(Base):
    __tablename__ = "deletion_records"
    __table_args__ = (Index("ix_deletion_records_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    subject_ref: Mapped[str] = mapped_column(String(255))
    memory_items_deleted: Mapped[list[str]] = mapped_column(JSONType, default=list)
    deletion_proof_hash: Mapped[str] = mapped_column(String(64), default="")
    requested_by: Mapped[str] = mapped_column(String(255), default="")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
