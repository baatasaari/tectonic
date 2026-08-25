"""SQLAlchemy 2.0 declarative models for the PromptOps module data model
(LLD §3): PromptVersion, ABTest.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from promptops.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (Index("ix_prompt_versions_tenant_name", "tenant_id", "prompt_name"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    prompt_name: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(255))
    template: Mapped[str] = mapped_column(Text())
    status: Mapped[str] = mapped_column(String(16), default="draft")
    parent_version_id: Mapped[str | None] = mapped_column(UUIDType, nullable=True)
    promoted_pass_rate: Mapped[float | None] = mapped_column(Float(), nullable=True)
    promoted_sample_size: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class ABTest(Base):
    __tablename__ = "ab_tests"
    __table_args__ = (Index("ix_ab_tests_tenant_prompt", "tenant_id", "prompt_name"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    prompt_name: Mapped[str] = mapped_column(String(255))
    version_a_id: Mapped[str] = mapped_column(UUIDType)
    version_b_id: Mapped[str] = mapped_column(UUIDType)
    status: Mapped[str] = mapped_column(String(16), default="running")
    winner_version_id: Mapped[str | None] = mapped_column(UUIDType, nullable=True)
    p_value: Mapped[float | None] = mapped_column(Float(), nullable=True)
    sample_size_a: Mapped[int] = mapped_column(Integer(), default=0)
    sample_size_b: Mapped[int] = mapped_column(Integer(), default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    concluded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
