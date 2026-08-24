"""SQLAlchemy 2.0 declarative models for the Intent Detection data model
(LLD §3.1): IntentTaxonomy, ClassificationLog, DriftReport.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, Boolean, DateTime, Float, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from intent_detection.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class IntentTaxonomy(Base):
    __tablename__ = "intent_taxonomies"
    __table_args__ = (Index("ix_intent_taxonomies_tenant_version", "tenant_id", "version", unique=True),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer())
    intents: Mapped[list[dict]] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClassificationLog(Base):
    __tablename__ = "classification_logs"
    __table_args__ = (Index("ix_classification_logs_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    input_hash: Mapped[str] = mapped_column(String(64))
    taxonomy_version: Mapped[int] = mapped_column(Integer())
    intents_detected: Mapped[list[dict]] = mapped_column(JSONType, default=list)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DriftReport(Base):
    __tablename__ = "drift_reports"
    __table_args__ = (Index("ix_drift_reports_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    taxonomy_version: Mapped[int] = mapped_column(Integer())
    drift_score: Mapped[float] = mapped_column(Float())
    flagged_intents: Mapped[list[str]] = mapped_column(JSONType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
