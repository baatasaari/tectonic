"""SQLAlchemy 2.0 declarative models for the A2A module data model (LLD
§3): A2ATask, A2AAccessPolicy, AgentCardCache.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, DateTime, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from a2a_gateway.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class A2ATask(Base):
    __tablename__ = "a2a_tasks"
    __table_args__ = (Index("ix_a2a_tasks_tenant", "tenant_id"), Index("ix_a2a_tasks_direction", "direction"))

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    direction: Mapped[str] = mapped_column(String(16))
    peer_agent_url: Mapped[str] = mapped_column(String(2048))
    skill_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="submitted")
    input_message: Mapped[dict] = mapped_column(JSONType, default=dict)
    output_artifacts: Mapped[list] = mapped_column(JSONType, default=list)
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class A2AAccessPolicy(Base):
    __tablename__ = "a2a_access_policies"
    __table_args__ = (
        UniqueConstraint("caller_agent_id", "tenant_id", name="uq_a2a_access_policies_caller_tenant"),
        Index("ix_a2a_access_policies_caller_tenant", "caller_agent_id", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    caller_agent_id: Mapped[str] = mapped_column(String(255))
    tenant_id: Mapped[str] = mapped_column(String(255))
    allowed_skills: Mapped[list[str] | None] = mapped_column(JSONType, nullable=True)


class AgentCardCache(Base):
    __tablename__ = "agent_card_cache"
    __table_args__ = (UniqueConstraint("agent_url", name="uq_agent_card_cache_agent_url"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    agent_url: Mapped[str] = mapped_column(String(2048))
    card: Mapped[dict] = mapped_column(JSONType, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
