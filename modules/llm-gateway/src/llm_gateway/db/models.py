"""SQLAlchemy 2.0 declarative models for the LLM Gateway data model (LLD §3.1):
VirtualKey, BudgetPolicy, RequestLog, ProviderConfig.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from llm_gateway.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class VirtualKey(Base):
    __tablename__ = "virtual_keys"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    provider_scope: Mapped[list[str]] = mapped_column(JSONType, default=list)
    budget_policy_ref: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class BudgetPolicy(Base):
    __tablename__ = "budget_policies"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    period: Mapped[str] = mapped_column(String(16))
    limit_amount: Mapped[float] = mapped_column()
    current_spend: Mapped[float] = mapped_column(default=0.0)
    alert_threshold_pct: Mapped[float] = mapped_column(default=0.8)


class RequestLog(Base):
    __tablename__ = "request_logs"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    virtual_key_id: Mapped[str] = mapped_column(UUIDType)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cost: Mapped[float] = mapped_column(default=0.0)
    cache_hit: Mapped[bool] = mapped_column(default=False)
    latency_ms: Mapped[float] = mapped_column(default=0.0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ProviderConfig(Base):
    __tablename__ = "provider_configs"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    provider_name: Mapped[str] = mapped_column(String(64), unique=True)
    endpoint: Mapped[str] = mapped_column(String(512))
    priority: Mapped[int] = mapped_column(default=0)
    health_status: Mapped[str] = mapped_column(String(16), default="healthy")
    deprecation_notices: Mapped[list[dict]] = mapped_column(JSONType, default=list)
