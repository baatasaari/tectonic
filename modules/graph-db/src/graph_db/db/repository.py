"""SQLAlchemy-backed implementation of GraphRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from graph_db.core.domain import EdgeKind, EdgeRecord, NodeRecord
from graph_db.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    # SQLite (the unit-test/dev backend) returns naive datetimes even for
    # DateTime(timezone=True) columns; Postgres returns aware ones. The
    # Temporal Filter compares valid_from/valid_to against an aware
    # `as_of`, so every datetime crossing this boundary is normalised to
    # UTC-aware here, once, regardless of backend.
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _node_to_domain(m: models.Node) -> NodeRecord:
    return NodeRecord(
        id=str(m.id), tenant_id=m.tenant_id, entity_type=m.entity_type, name=m.name,
        attributes=dict(m.attributes or {}), created_at=_as_utc(m.created_at),
    )


def _edge_to_domain(m: models.Edge) -> EdgeRecord:
    return EdgeRecord(
        id=str(m.id), tenant_id=m.tenant_id, from_node_id=str(m.from_node_id), to_node_id=str(m.to_node_id),
        relationship_type=m.relationship_type, edge_kind=EdgeKind(m.edge_kind), valid_from=_as_utc(m.valid_from),
        valid_to=_as_utc(m.valid_to), confidence=m.confidence, source_ref=m.source_ref,
        created_at=_as_utc(m.created_at),
    )


class SQLAlchemyGraphRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_node(self, record: NodeRecord) -> NodeRecord:
        m = models.Node(
            id=record.id, tenant_id=record.tenant_id, entity_type=record.entity_type, name=record.name,
            attributes=record.attributes,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _node_to_domain(m)

    async def get_node(self, tenant_id: str, node_id: str) -> NodeRecord | None:
        m = await self.session.get(models.Node, node_id)
        if m is None or m.tenant_id != tenant_id:
            return None
        return _node_to_domain(m)

    async def create_edge(self, record: EdgeRecord) -> EdgeRecord:
        m = models.Edge(
            id=record.id, tenant_id=record.tenant_id, from_node_id=record.from_node_id,
            to_node_id=record.to_node_id, relationship_type=record.relationship_type,
            edge_kind=record.edge_kind.value, valid_from=record.valid_from, valid_to=record.valid_to,
            confidence=record.confidence, source_ref=record.source_ref,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _edge_to_domain(m)

    async def list_outgoing_edges(self, tenant_id: str, node_id: str) -> list[EdgeRecord]:
        rows = await self.session.execute(
            select(models.Edge).where(models.Edge.tenant_id == tenant_id, models.Edge.from_node_id == node_id)
        )
        return [_edge_to_domain(m) for m in rows.scalars().all()]

    async def list_incoming_edges(self, tenant_id: str, node_id: str) -> list[EdgeRecord]:
        rows = await self.session.execute(
            select(models.Edge).where(models.Edge.tenant_id == tenant_id, models.Edge.to_node_id == node_id)
        )
        return [_edge_to_domain(m) for m in rows.scalars().all()]

    async def count_nodes(self, tenant_id: str) -> int:
        rows = await self.session.execute(select(models.Node).where(models.Node.tenant_id == tenant_id))
        return len(rows.scalars().all())

    async def count_edges_by_kind(self, tenant_id: str) -> dict[str, int]:
        rows = await self.session.execute(select(models.Edge).where(models.Edge.tenant_id == tenant_id))
        counts: dict[str, int] = {}
        for m in rows.scalars().all():
            counts[m.edge_kind] = counts.get(m.edge_kind, 0) + 1
        return counts
