"""SQLAlchemy 2.0 declarative models for the Agent Cards module data
model (LLD §3): AgentCard.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, DateTime, Float, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from agent_cards.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class AgentCard(Base):
    __tablename__ = "agent_cards"
    __table_args__ = (
        UniqueConstraint("tenant_id", "agent_ref", name="uq_agent_cards_tenant_agent_ref"),
        Index("ix_agent_cards_tenant", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    agent_ref: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text())
    url: Mapped[str] = mapped_column(String(2048))
    skills: Mapped[list] = mapped_column(JSONType, default=list)
    trust_score: Mapped[float | None] = mapped_column(Float(), nullable=True)
    trust_score_computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
