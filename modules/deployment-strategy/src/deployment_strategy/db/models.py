"""SQLAlchemy 2.0 declarative models for the Deployment Strategy module
data model (LLD §3): Deployment.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from deployment_strategy.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class Deployment(Base):
    __tablename__ = "deployments"
    __table_args__ = (
        Index("ix_deployments_tenant_service_target", "tenant_id", "service_name", "target"),
        Index("ix_deployments_stage", "stage"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    service_name: Mapped[str] = mapped_column(String(255))
    build_ref: Mapped[str] = mapped_column(String(255))
    target: Mapped[str] = mapped_column(String(255))
    canary_percentage: Mapped[int] = mapped_column(Integer(), default=10)
    budget_policy_id: Mapped[str | None] = mapped_column(UUIDType, nullable=True)
    stage: Mapped[str] = mapped_column(String(32), default="canary")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rollback_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
