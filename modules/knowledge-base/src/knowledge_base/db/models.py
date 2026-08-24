"""SQLAlchemy 2.0 declarative models for the Knowledge Base data model
(LLD §3): Document, DocumentVersion, Chunk, PolicyTag.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from knowledge_base.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(512))
    source_type: Mapped[str] = mapped_column(String(16), default="upload")
    current_version_id: Mapped[str | None] = mapped_column(UUIDType, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    staleness_threshold_days: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    last_reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (Index("ix_document_versions_document", "document_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    document_id: Mapped[str] = mapped_column(UUIDType)
    content_hash: Mapped[str] = mapped_column(String(64))
    blob_ref: Mapped[str] = mapped_column(String(255))
    version_number: Mapped[int] = mapped_column(Integer())
    created_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (Index("ix_chunks_version", "document_version_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    document_version_id: Mapped[str] = mapped_column(UUIDType)
    content: Mapped[str] = mapped_column(Text())
    chunk_index: Mapped[int] = mapped_column(Integer())
    policy_tags: Mapped[list[str]] = mapped_column(JSONType, default=list)
    token_count: Mapped[int] = mapped_column(Integer(), default=0)


class PolicyTag(Base):
    __tablename__ = "policy_tags"
    __table_args__ = (Index("ix_policy_tags_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(1024), default="")
