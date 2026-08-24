"""Integration tier (LLD §4 testing plan): the SQLAlchemy repository
against a real Postgres — not part of the default unit-test run. See
`conftest.py` for how the Postgres instance is obtained.

Specifically exercises what SQLite's unit-tier tests can't: real JSONB
list round-tripping (`Alert.agent_refs`), an upsert-style query
(`upsert_baseline`) that must update only the one row matching a real
multi-column uniqueness constraint (`tenant_id`, `agent_ref`,
`action_type`) rather than creating a duplicate, and a multi-row filtered
query (`list_alerts` scoped by severity) against genuine Postgres
semantics.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from sentinel_agents.core.domain import (
    AgentBaselineRecord,
    AlertRecord,
    AlertType,
    Severity,
    new_id,
)
from sentinel_agents.db import models
from sentinel_agents.db.repository import SQLAlchemySentinelRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["SENTINEL_AGENTS_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_alert_agent_refs_round_trip_as_real_jsonb(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemySentinelRepository(session)
            agent_refs = ["agent-alpha", "agent-beta", "agent-gamma"]
            created = await repo.create_alert(
                AlertRecord(
                    id=new_id(), tenant_id="acme", alert_type=AlertType.SWARM, agent_refs=agent_refs,
                    severity=Severity.HIGH, description="coordinated tool-call spike",
                )
            )
            assert created.agent_refs == agent_refs

            # A real JSONB round trip preserves list order and element types exactly —
            # this is exactly the kind of thing SQLite's JSON-as-TEXT variant can
            # silently get away with getting wrong that Postgres's native JSONB won't.
            fetched = await repo.get_alert("acme", created.id)
            assert fetched is not None
            assert fetched.agent_refs == agent_refs
    finally:
        await engine.dispose()


async def test_upsert_baseline_updates_only_the_matching_row(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemySentinelRepository(session)
            # a sibling baseline for the same agent but a different action_type, which
            # must be left untouched by the upserts below.
            sibling = await repo.upsert_baseline(
                "acme", AgentBaselineRecord(agent_ref="agent-alpha", action_type="tool_call", mean=1.0, sample_count=1)
            )
            first = await repo.upsert_baseline(
                "acme", AgentBaselineRecord(agent_ref="agent-alpha", action_type="api_call", mean=5.0, sample_count=1)
            )
            updated = await repo.upsert_baseline(
                "acme",
                AgentBaselineRecord(agent_ref="agent-alpha", action_type="api_call", mean=7.5, m2=3.2, sample_count=2),
            )

            # multi-row upsert-style query hitting only the intended row: same
            # (tenant_id, agent_ref, action_type) must update the existing row in place,
            # not create a second row alongside it — a real uniqueness/identity guarantee
            # Postgres enforces that a fake in-memory repository can't meaningfully prove.
            rows = (await session.execute(select(models.AgentBaseline))).scalars().all()
            assert len(rows) == 2
            assert updated.mean == 7.5
            assert updated.sample_count == 2

            unchanged_sibling = await repo.get_baseline("acme", "agent-alpha", "tool_call")
            assert unchanged_sibling is not None
            assert unchanged_sibling.mean == sibling.mean == 1.0

            refreshed = await repo.get_baseline("acme", "agent-alpha", "api_call")
            assert refreshed is not None
            assert refreshed.mean == 7.5
            assert refreshed.sample_count == 2
            assert first.mean == 5.0  # the pre-update snapshot is untouched
    finally:
        await engine.dispose()


async def test_list_alerts_filters_by_severity_across_multiple_rows(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemySentinelRepository(session)
            # a tenant distinct from the other tests in this module, so this test's
            # filter assertion isn't polluted by alerts those tests created.
            high = await repo.create_alert(
                AlertRecord(
                    id=new_id(), tenant_id="sev-tenant", alert_type=AlertType.SINGLE_AGENT, agent_refs=["a1"],
                    severity=Severity.HIGH, description="high severity",
                )
            )
            await repo.create_alert(
                AlertRecord(
                    id=new_id(), tenant_id="sev-tenant", alert_type=AlertType.SINGLE_AGENT, agent_refs=["a2"],
                    severity=Severity.LOW, description="low severity",
                )
            )
            other_tenant_high = await repo.create_alert(
                AlertRecord(
                    id=new_id(), tenant_id="other", alert_type=AlertType.SINGLE_AGENT, agent_refs=["a3"],
                    severity=Severity.HIGH, description="other tenant high severity",
                )
            )

            results = await repo.list_alerts("sev-tenant", severity="high")
            result_ids = {r.id for r in results}
            assert result_ids == {high.id}
            assert other_tenant_high.id not in result_ids
    finally:
        await engine.dispose()
