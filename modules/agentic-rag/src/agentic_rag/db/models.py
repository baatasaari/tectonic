"""SQLAlchemy 2.0 declarative models for the Agentic RAG data model
(LLD §3.1): RetrievalRequest, RetrievalHop, RetrievalResult.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from agentic_rag.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class RetrievalRequest(Base):
    __tablename__ = "retrieval_requests"
    __table_args__ = (Index("ix_retrieval_requests_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    query: Mapped[str] = mapped_column(String())
    scope: Mapped[list[str]] = mapped_column(JSONType, default=list)
    max_hops: Mapped[int] = mapped_column(Integer(), default=3)
    groundedness_threshold: Mapped[float] = mapped_column(Float(), default=0.85)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RetrievalHop(Base):
    __tablename__ = "retrieval_hops"
    __table_args__ = (Index("ix_retrieval_hops_request", "request_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    request_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("retrieval_requests.id"))
    hop_number: Mapped[int] = mapped_column(Integer())
    reformulated_query: Mapped[str | None] = mapped_column(String(), nullable=True)
    retrieved_items: Mapped[list[dict]] = mapped_column(JSONType, default=list)
    groundedness_score: Mapped[float] = mapped_column(Float())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RetrievalResult(Base):
    __tablename__ = "retrieval_results"

    request_id: Mapped[str] = mapped_column(UUIDType, primary_key=True)
    final_context: Mapped[str] = mapped_column(String())
    total_hops: Mapped[int] = mapped_column(Integer())
    final_groundedness_score: Mapped[float] = mapped_column(Float())
    provenance_chain: Mapped[list[dict]] = mapped_column(JSONType, default=list)
    outcome: Mapped[str] = mapped_column(String(32))
