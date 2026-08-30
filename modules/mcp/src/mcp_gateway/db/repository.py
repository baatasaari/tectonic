"""SQLAlchemy-backed implementation of MCPGatewayRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mcp_gateway.core.domain import (
    AccessPolicyRecord,
    McpServerRecord,
    McpToolRecord,
    ServerStatus,
)
from mcp_gateway.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _server_to_domain(m: models.McpServer) -> McpServerRecord:
    return McpServerRecord(
        id=str(m.id), tenant_id=m.tenant_id, name=m.name, description=m.description, base_url=m.base_url,
        status=ServerStatus(m.status), created_at=_as_utc(m.created_at),
    )


def _tool_to_domain(m: models.McpTool) -> McpToolRecord:
    return McpToolRecord(
        id=str(m.id), server_id=str(m.server_id), name=m.name, description=m.description,
        input_schema=dict(m.input_schema or {}), synced_at=_as_utc(m.synced_at),
    )


def _policy_to_domain(m: models.AccessPolicy) -> AccessPolicyRecord:
    return AccessPolicyRecord(
        id=str(m.id), server_id=str(m.server_id), tenant_id=m.tenant_id,
        allowed_tools=list(m.allowed_tools) if m.allowed_tools is not None else None,
    )


class SQLAlchemyMCPGatewayRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_server(self, record: McpServerRecord) -> McpServerRecord:
        m = models.McpServer(
            id=record.id, tenant_id=record.tenant_id, name=record.name, description=record.description,
            base_url=record.base_url, status=record.status.value,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _server_to_domain(m)

    async def get_server(self, server_id: str) -> McpServerRecord | None:
        m = await self.session.get(models.McpServer, server_id)
        return _server_to_domain(m) if m else None

    async def list_servers(
        self, *, tenant_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[McpServerRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.McpServer.tenant_id == tenant_id)

        count_stmt = select(func.count(models.McpServer.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.McpServer)
            .where(*filters)
            .order_by(models.McpServer.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_server_to_domain(m) for m in rows.scalars().all()], total

    async def replace_tools(self, server_id: str, tools: list[McpToolRecord]) -> None:
        await self.session.execute(delete(models.McpTool).where(models.McpTool.server_id == server_id))
        for t in tools:
            self.session.add(models.McpTool(
                id=t.id, server_id=server_id, name=t.name, description=t.description, input_schema=t.input_schema,
            ))
        await self.session.commit()

    async def list_tools(self, server_id: str) -> list[McpToolRecord]:
        rows = await self.session.execute(
            select(models.McpTool).where(models.McpTool.server_id == server_id).order_by(models.McpTool.name)
        )
        return [_tool_to_domain(m) for m in rows.scalars().all()]

    async def upsert_access_policy(self, record: AccessPolicyRecord) -> AccessPolicyRecord:
        rows = await self.session.execute(
            select(models.AccessPolicy).where(
                models.AccessPolicy.server_id == record.server_id,
                models.AccessPolicy.tenant_id == record.tenant_id,
            )
        )
        existing = rows.scalars().first()
        if existing is not None:
            existing.allowed_tools = record.allowed_tools
            await self.session.commit()
            await self.session.refresh(existing)
            return _policy_to_domain(existing)

        m = models.AccessPolicy(
            id=record.id, server_id=record.server_id, tenant_id=record.tenant_id, allowed_tools=record.allowed_tools,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _policy_to_domain(m)

    async def get_access_policy(self, server_id: str, tenant_id: str) -> AccessPolicyRecord | None:
        rows = await self.session.execute(
            select(models.AccessPolicy).where(
                models.AccessPolicy.server_id == server_id, models.AccessPolicy.tenant_id == tenant_id,
            )
        )
        m = rows.scalars().first()
        return _policy_to_domain(m) if m else None
