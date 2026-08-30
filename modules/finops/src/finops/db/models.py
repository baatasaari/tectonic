"""SQLAlchemy 2.0 declarative models for the FinOps module data model
(LLD §3): UsageEvent, BudgetPolicy, OptimisationAction.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, DateTime, Float, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from finops.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (Index("ix_usage_events_tenant_occurred", "tenant_id", "occurred_at"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    source_module: Mapped[str] = mapped_column(String(255))
    resource_type: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[float] = mapped_column(Float())
    unit_cost: Mapped[float] = mapped_column(Float())
    cost: Mapped[float] = mapped_column(Float())
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BudgetPolicy(Base):
    __tablename__ = "budget_policies"
    __table_args__ = (Index("ix_budget_policies_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    period: Mapped[str] = mapped_column(String(16))
    limit_amount: Mapped[float] = mapped_column(Float())
    alert_threshold_pct: Mapped[float] = mapped_column(Float(), default=0.8)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class OptimisationAction(Base):
    __tablename__ = "optimisation_actions"
    __table_args__ = (Index("ix_optimisation_actions_policy", "budget_policy_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    budget_policy_id: Mapped[str] = mapped_column(UUIDType)
    action_type: Mapped[str] = mapped_column(String(64))
    previous_value: Mapped[float] = mapped_column(Float())
    new_value: Mapped[float] = mapped_column(Float())
    reason: Mapped[str] = mapped_column(Text())
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
