"""SQLAlchemy 2.0 declarative models for the Context Engineering data model
(LLD §3.1): OntologyConfig, PrioritisationWeights, ContextAssembly.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from context_engineering.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class OntologyConfig(Base):
    __tablename__ = "ontology_configs"
    __table_args__ = (Index("ix_ontology_configs_tenant_version", "tenant_id", "version", unique=True),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer())
    roles: Mapped[list[str]] = mapped_column(JSONType, default=list)
    entity_types: Mapped[list[str]] = mapped_column(JSONType, default=list)
    policy_tags: Mapped[list[str]] = mapped_column(JSONType, default=list)


class PrioritisationWeights(Base):
    __tablename__ = "prioritisation_weights"
    __table_args__ = (Index("ix_prioritisation_weights_tenant_task", "tenant_id", "task_type", unique=True),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    task_type: Mapped[str] = mapped_column(String(255))
    feature_weights: Mapped[dict] = mapped_column(JSONType, default=dict)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContextAssembly(Base):
    __tablename__ = "context_assemblies"
    __table_args__ = (Index("ix_context_assemblies_request_ref", "request_ref"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    request_ref: Mapped[str] = mapped_column(String(255))
    task_type: Mapped[str] = mapped_column(String(255))
    items_included: Mapped[list[dict]] = mapped_column(JSONType, default=list)
    items_dropped: Mapped[list[dict]] = mapped_column(JSONType, default=list)
    items_summarised: Mapped[list[dict]] = mapped_column(JSONType, default=list)
    total_tokens_used: Mapped[int] = mapped_column(Integer(), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
