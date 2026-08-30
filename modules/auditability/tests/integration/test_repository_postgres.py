"""Integration tier: proves things SQLite's unit-tier fakes can't reliably
prove -- real JSONB payload round-tripping and querying (including the
`payload->>'control_name'` filter Module 17 already depends on), and a
genuine multi-entry hash chain built and verified against real Postgres.
See `conftest.py` for how the Postgres instance is obtained.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from auditability.core.chain_verifier import verify_chain
from auditability.core.domain import AuditEventFilter
from auditability.db.repository import SQLAlchemyAuditabilityRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["AUDITABILITY_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_payload_round_trips_as_real_jsonb_with_nested_structure(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyAuditabilityRepository(session)
            payload = {"event_type": "oversight_override", "detail": {"nested": ["a", "b"], "n": 3}}
            event = await repo.append_event(
                tenant_id="acme", source_module="human-oversight", event_type="oversight_override", payload=payload,
            )

            fetched = await repo.list_events_for_chain("acme")

            assert len(fetched) == 1
            # Real JSONB round trip preserves nested dict/list structure and types exactly
            # -- SQLite's JSON-as-TEXT variant can silently get this wrong.
            assert fetched[0].payload == payload
            assert fetched[0].entry_hash == event.entry_hash
    finally:
        await engine.dispose()


async def test_a_genuine_multi_entry_chain_verifies_against_real_postgres(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyAuditabilityRepository(session)
            for i in range(5):
                await repo.append_event(
                    tenant_id="chain-tenant", source_module="workflow-engine", event_type="step", payload={"i": i},
                )

            events = await repo.list_events_for_chain("chain-tenant")
            result = verify_chain(events)

            assert result.valid is True
            assert result.verified_count == 5
    finally:
        await engine.dispose()


async def test_list_events_filters_by_control_name_inside_the_jsonb_payload(migrated_url):
    """The exact query shape Module 17 (Regulatory and Compliance) already codes
    against: GET /events?control_name=... filters on a key *inside* the opaque
    payload, not a first-class column."""
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyAuditabilityRepository(session)
            await repo.append_event(
                tenant_id="filter-tenant", source_module="regulatory-compliance", event_type="control_implemented",
                payload={"control_name": "human_oversight"},
            )
            await repo.append_event(
                tenant_id="filter-tenant", source_module="regulatory-compliance", event_type="control_implemented",
                payload={"control_name": "audit_logging"},
            )

            matching, total = await repo.list_events(
                AuditEventFilter(tenant_id="filter-tenant", control_name="human_oversight")
            )

            assert total == 1
            assert matching[0].payload["control_name"] == "human_oversight"
    finally:
        await engine.dispose()


async def test_list_events_pagination_hits_only_the_intended_rows(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyAuditabilityRepository(session)
            for i in range(5):
                await repo.append_event(
                    tenant_id="page-tenant", source_module="m1", event_type="e", payload={"i": i},
                )

            page1, total1 = await repo.list_events(AuditEventFilter(tenant_id="page-tenant", limit=2, offset=0))
            page2, total2 = await repo.list_events(AuditEventFilter(tenant_id="page-tenant", limit=2, offset=2))

            assert total1 == total2 == 5
            assert len(page1) == 2
            assert len(page2) == 2
            assert {e.id for e in page1}.isdisjoint({e.id for e in page2})
            # newest first
            assert page1[0].sequence_number == 5
    finally:
        await engine.dispose()
