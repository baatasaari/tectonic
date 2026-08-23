"""SQLAlchemy 2.0 declarative models physically backing the Graph DB's
logical graph schema (LLD §3) — see the module README's "Design notes vs.
the LLD" for why a relational table pair stands in for Neo4j/Memgraph.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, DateTime, Float, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from graph_db.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class Node(Base):
    __tablename__ = "nodes"
    __table_args__ = (Index("ix_nodes_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    entity_type: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(512))
    attributes: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Edge(Base):
    __tablename__ = "edges"
    __table_args__ = (
        Index("ix_edges_tenant_from", "tenant_id", "from_node_id"),
        Index("ix_edges_tenant_to", "tenant_id", "to_node_id"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    from_node_id: Mapped[str] = mapped_column(UUIDType)
    to_node_id: Mapped[str] = mapped_column(UUIDType)
    relationship_type: Mapped[str] = mapped_column(String(128))
    edge_kind: Mapped[str] = mapped_column(String(16))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float(), nullable=True)
    source_ref: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
