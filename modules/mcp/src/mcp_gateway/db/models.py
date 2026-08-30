"""SQLAlchemy 2.0 declarative models for the MCP module data model (LLD
§3): McpServer, McpTool, AccessPolicy.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, JSON, DateTime, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mcp_gateway.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


JSONType = JSONB().with_variant(JSON(), "sqlite")
UUIDType = UUID(as_uuid=False).with_variant(CHAR(36), "sqlite")


class McpServer(Base):
    __tablename__ = "mcp_servers"
    __table_args__ = (Index("ix_mcp_servers_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    tenant_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text())
    base_url: Mapped[str] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class McpTool(Base):
    __tablename__ = "mcp_tools"
    __table_args__ = (Index("ix_mcp_tools_server", "server_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    server_id: Mapped[str] = mapped_column(UUIDType)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text())
    input_schema: Mapped[dict] = mapped_column(JSONType, default=dict)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccessPolicy(Base):
    __tablename__ = "access_policies"
    __table_args__ = (
        UniqueConstraint("server_id", "tenant_id", name="uq_access_policies_server_tenant"),
        Index("ix_access_policies_server_tenant", "server_id", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=_new_id)
    server_id: Mapped[str] = mapped_column(UUIDType)
    tenant_id: Mapped[str] = mapped_column(String(255))
    allowed_tools: Mapped[list[str] | None] = mapped_column(JSONType, nullable=True)
