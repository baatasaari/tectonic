"""SQLAlchemy 2.0 declarative models for the Multi-modality module data
model (LLD §3): Extraction.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, DateTime, Float, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from multi_modality.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class Extraction(Base):
    __tablename__ = "extractions"
    __table_args__ = (Index("ix_extractions_tenant_modality", "tenant_id", "modality"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    modality: Mapped[str] = mapped_column(String(16))
    raw_content: Mapped[str] = mapped_column(Text())
    extracted_content: Mapped[str] = mapped_column(Text())
    grounding_context: Mapped[str | None] = mapped_column(Text(), nullable=True)
    groundedness_decision: Mapped[str] = mapped_column(String(16), default="not_checked")
    groundedness_violation_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float(), default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
