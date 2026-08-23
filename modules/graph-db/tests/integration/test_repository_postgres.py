"""Integration tier (LLD §4 testing plan): the SQLAlchemy repository
against a real Postgres — not part of the default unit-test run. See
`conftest.py` for how the Postgres instance is obtained.

Specifically exercises what SQLite's unit-tier tests can't: real JSONB
dict round-tripping (`Node.attributes`, including nested lists/dicts),
a real UUID primary key/foreign key relationship between two nodes and
the edge that connects them, and a multi-row aggregation
(`count_edges_by_kind`) that must only see the querying tenant's rows
against genuine Postgres semantics.
"""
from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from graph_db.core.domain import EdgeKind, EdgeRecord, NodeRecord, new_id
from graph_db.db.repository import SQLAlchemyGraphRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["GRAPH_DB_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_node_attributes_round_trip_as_real_jsonb(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyGraphRepository(session)
            attrs = {"tags": ["fraud", "reviewed"], "risk_score": 0.72, "meta": {"source": "case-1928"}}
            created = await repo.create_node(
                NodeRecord(id=new_id(), tenant_id="acme", entity_type="case", name="Case 1928", attributes=attrs)
            )
            assert created.attributes == attrs

            # A real JSONB round trip preserves nested list/dict structure and element
            # types exactly — this is exactly the kind of thing SQLite's JSON-as-TEXT
            # variant can silently get away with getting wrong that Postgres's native
            # JSONB type won't.
            fetched = await repo.get_node("acme", created.id)
            assert fetched is not None
            assert fetched.attributes == attrs
            assert fetched.attributes["tags"] == ["fraud", "reviewed"]
    finally:
        await engine.dispose()


async def test_edge_creation_round_trips_real_uuid_foreign_keys(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyGraphRepository(session)
            source = await repo.create_node(
                NodeRecord(id=new_id(), tenant_id="acme", entity_type="person", name="Alice")
            )
            target = await repo.create_node(
                NodeRecord(id=new_id(), tenant_id="acme", entity_type="person", name="Bob")
            )
            edge = await repo.create_edge(
                EdgeRecord(
                    id=new_id(), tenant_id="acme", from_node_id=source.id, to_node_id=target.id,
                    relationship_type="reports_to", edge_kind=EdgeKind.STRUCTURAL,
                )
            )
            # A real UUID primary key (asyncpg returns/accepts a genuine UUID type;
            # SQLite's CHAR(36) variant just stores a plain string) — confirm the edge's
            # from/to columns round-trip as fetchable foreign keys into the real node PKs,
            # not just strings that happen to look like the right ones.
            assert edge.from_node_id == source.id
            assert edge.to_node_id == target.id

            outgoing = await repo.list_outgoing_edges("acme", source.id)
            assert [e.id for e in outgoing] == [edge.id]
            assert outgoing[0].to_node_id == target.id

            incoming = await repo.list_incoming_edges("acme", target.id)
            assert [e.id for e in incoming] == [edge.id]
            assert incoming[0].from_node_id == source.id
    finally:
        await engine.dispose()


async def test_count_edges_by_kind_aggregates_only_tenant_rows(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyGraphRepository(session)
            # a tenant distinct from the other tests in this module, so this test's
            # aggregation isn't polluted by edges those tests created.
            a = await repo.create_node(NodeRecord(id=new_id(), tenant_id="agg-tenant", entity_type="x", name="A"))
            b = await repo.create_node(NodeRecord(id=new_id(), tenant_id="agg-tenant", entity_type="x", name="B"))
            other_a = await repo.create_node(NodeRecord(id=new_id(), tenant_id="other", entity_type="x", name="A2"))
            other_b = await repo.create_node(NodeRecord(id=new_id(), tenant_id="other", entity_type="x", name="B2"))

            await repo.create_edge(
                EdgeRecord(
                    id=new_id(), tenant_id="agg-tenant", from_node_id=a.id, to_node_id=b.id,
                    relationship_type="r1", edge_kind=EdgeKind.CAUSAL,
                )
            )
            await repo.create_edge(
                EdgeRecord(
                    id=new_id(), tenant_id="agg-tenant", from_node_id=b.id, to_node_id=a.id,
                    relationship_type="r2", edge_kind=EdgeKind.CAUSAL,
                )
            )
            await repo.create_edge(
                EdgeRecord(
                    id=new_id(), tenant_id="agg-tenant", from_node_id=a.id, to_node_id=b.id,
                    relationship_type="r3", edge_kind=EdgeKind.CORRELATIONAL,
                )
            )
            # a same-shaped edge for a different tenant — must not leak into agg-tenant's count
            await repo.create_edge(
                EdgeRecord(
                    id=new_id(), tenant_id="other", from_node_id=other_a.id, to_node_id=other_b.id,
                    relationship_type="r1", edge_kind=EdgeKind.CAUSAL,
                )
            )

            counts = await repo.count_edges_by_kind("agg-tenant")
            assert counts == {"causal": 2, "correlational": 1}
    finally:
        await engine.dispose()
