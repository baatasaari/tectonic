"""SQLAlchemy 2.0 declarative models for the Agent Marketplace module
data model (LLD §3): AgentMarketplaceListing, UsageEvent.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, Boolean, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from agent_marketplace.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class AgentMarketplaceListing(Base):
    __tablename__ = "agent_marketplace_listings"
    __table_args__ = (
        Index("ix_agent_marketplace_listings_tenant", "tenant_id"),
        Index("ix_agent_marketplace_listings_status", "status"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    agent_card_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text())
    skills_snapshot: Mapped[list] = mapped_column(JSONType, default=list)
    trust_score_snapshot: Mapped[float | None] = mapped_column(Float(), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending_review")
    submitted_by: Mapped[str] = mapped_column(String(255), default="")
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    reuse_count: Mapped[int] = mapped_column(Integer(), default=0)
    external_listing_enabled: Mapped[bool] = mapped_column(Boolean(), default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class UsageEvent(Base):
    __tablename__ = "agent_marketplace_usage_events"
    __table_args__ = (Index("ix_agent_marketplace_usage_events_listing", "listing_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    listing_id: Mapped[str] = mapped_column(UUIDType)
    consumer_tenant_id: Mapped[str] = mapped_column(String(255))
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
