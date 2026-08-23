"""SQLAlchemy-backed implementation of ToolRepository (LLD §3.1)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tool_orchestration.core.domain import (
    ReliabilityScoreRecord,
    ToolDefinitionRecord,
    ToolInvocationRecord,
    ToolStatus,
)
from tool_orchestration.db import models


def _tool_to_domain(m: models.ToolDefinition) -> ToolDefinitionRecord:
    return ToolDefinitionRecord(
        id=str(m.id), tenant_id=m.tenant_id, name=m.name, mcp_server_ref=m.mcp_server_ref,
        schema=dict(m.schema_ or {}), status=ToolStatus(m.status), synthesised=m.synthesised, created_at=m.created_at,
    )


def _score_to_domain(m: models.ReliabilityScore) -> ReliabilityScoreRecord:
    return ReliabilityScoreRecord(
        tool_id=str(m.tool_id), rolling_success_rate=m.rolling_success_rate,
        rolling_avg_latency_ms=m.rolling_avg_latency_ms, last_updated_at=m.last_updated_at,
    )


class SQLAlchemyToolRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_tool_definition(self, record: ToolDefinitionRecord) -> ToolDefinitionRecord:
        m = models.ToolDefinition(
            id=record.id, tenant_id=record.tenant_id, name=record.name, mcp_server_ref=record.mcp_server_ref,
            schema_=record.schema, status=record.status.value, synthesised=record.synthesised,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _tool_to_domain(m)

    async def get_tool_definition(self, tool_id: str) -> ToolDefinitionRecord | None:
        m = await self.session.get(models.ToolDefinition, tool_id)
        return _tool_to_domain(m) if m else None

    async def update_tool_definition(self, record: ToolDefinitionRecord) -> ToolDefinitionRecord:
        m = await self.session.get(models.ToolDefinition, record.id)
        if m is None:
            raise LookupError(record.id)
        m.status = record.status.value
        m.schema_ = record.schema
        await self.session.commit()
        await self.session.refresh(m)
        return _tool_to_domain(m)

    async def list_tool_definitions(self, tenant_id: str, status: str | None = None) -> list[ToolDefinitionRecord]:
        stmt = select(models.ToolDefinition).where(models.ToolDefinition.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(models.ToolDefinition.status == status)
        rows = await self.session.execute(stmt)
        return [_tool_to_domain(m) for m in rows.scalars().all()]

    async def create_tool_invocation(self, record: ToolInvocationRecord) -> ToolInvocationRecord:
        m = models.ToolInvocation(
            id=record.id, tool_id=record.tool_id, agent_ref=record.agent_ref,
            workflow_instance_id=record.workflow_instance_id, status=record.status.value,
            retry_count=record.retry_count, latency_ms=record.latency_ms,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return record

    async def get_reliability_score(self, tool_id: str) -> ReliabilityScoreRecord | None:
        m = await self.session.get(models.ReliabilityScore, tool_id)
        return _score_to_domain(m) if m else None

    async def upsert_reliability_score(self, record: ReliabilityScoreRecord) -> ReliabilityScoreRecord:
        m = await self.session.get(models.ReliabilityScore, record.tool_id)
        if m is None:
            m = models.ReliabilityScore(
                tool_id=record.tool_id, rolling_success_rate=record.rolling_success_rate,
                rolling_avg_latency_ms=record.rolling_avg_latency_ms,
            )
            self.session.add(m)
        else:
            m.rolling_success_rate = record.rolling_success_rate
            m.rolling_avg_latency_ms = record.rolling_avg_latency_ms
        await self.session.commit()
        await self.session.refresh(m)
        return _score_to_domain(m)
