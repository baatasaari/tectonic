"""Integration tier (LLD's own testing plan): the SQLAlchemy repository
against a real Postgres — not part of the default unit-test run. See
`conftest.py` for how the Postgres instance is obtained.

Specifically exercises what SQLite's unit-tier tests can't: real JSONB
round-tripping of nested span `attributes` (mixed ints/floats/strings/
lists — the OTel extension attributes like `gen_ai.usage.input_tokens`,
`llm_gateway.cost`) with exact type preservation, a real `trace_id`/
`span_id` round trip, and two multi-row queries — `list_spans_for_trace`
filtered by both tenant *and* trace, and `list_traces_for_tenant`'s
`DISTINCT` over many spans per trace — that must return only the
intended rows/trace ids, not every row in the table.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from observability.core.domain import SpanRecord
from observability.db.repository import SQLAlchemyObservabilityRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["OBSERVABILITY_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


def _span(**overrides) -> SpanRecord:
    start = datetime.now(UTC)
    defaults = {
        "id": f"span-{overrides.get('span_id', 'x')}", "tenant_id": "acme", "trace_id": "trace-1",
        "span_id": "span-1", "parent_span_id": None, "name": "llm_gateway.complete",
        "service_name": "llm-gateway", "start_time": start,
        "end_time": start + timedelta(milliseconds=250), "ingested_at": start,
    }
    defaults.update(overrides)
    return SpanRecord(**defaults)


async def test_span_attributes_round_trip_as_real_jsonb_with_real_trace_span_ids(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyObservabilityRepository(session)
            attributes = {
                "gen_ai.usage.input_tokens": 512,
                "gen_ai.usage.output_tokens": 128,
                "llm_gateway.cost": 0.0034,
                "workflow.step_id": "step-7",
                "tool_calls": ["search_docs", "send_email"],
                "retry": {"count": 0, "last_error": None},
            }
            record = _span(
                id="span-attrs-1", trace_id="trace-abc123", span_id="span-def456",
                attributes=attributes,
            )
            created = await repo.create_span(record)
            # A real JSONB round trip preserves nested dict/list structure and exact
            # numeric types (int stays int, float stays float, null stays null) — the
            # kind of thing SQLite's JSON-as-TEXT variant can silently get wrong that
            # Postgres's native JSONB type won't.
            assert created.attributes == attributes
            assert isinstance(created.attributes["gen_ai.usage.input_tokens"], int)
            assert isinstance(created.attributes["llm_gateway.cost"], float)

            # trace_id/span_id are plain strings in this schema (following OTel's own
            # hex-string convention, not a UUID column) — confirm they round-trip
            # byte-for-byte through a real Postgres write/read, not just in memory.
            [fetched] = await repo.list_spans_for_trace("acme", "trace-abc123")
            assert fetched.trace_id == "trace-abc123"
            assert fetched.span_id == "span-def456"
            assert fetched.attributes == attributes

            # Regression check for a real schema-drift bug: the span time columns
            # were mapped without `DateTime(timezone=True)` even though the Alembic
            # migration (and the domain's own tz-aware `now()` default) both assume
            # a timestamptz column — invisible under SQLite, but asyncpg rejected
            # every write using an aware datetime against real Postgres. Fixed in
            # db/models.py; this asserts the round trip stays timezone-aware.
            assert created.start_time.tzinfo is not None
            assert fetched.start_time.tzinfo is not None
    finally:
        await engine.dispose()


async def test_list_spans_for_trace_matches_only_intended_tenant_and_trace(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyObservabilityRepository(session)

            target1 = await repo.create_span(_span(id="s1", trace_id="trace-x", span_id="span-1"))
            target2 = await repo.create_span(
                _span(id="s2", trace_id="trace-x", span_id="span-2", parent_span_id="span-1")
            )
            # Same tenant, different trace -> must NOT be returned.
            other_trace = await repo.create_span(_span(id="s3", trace_id="trace-y", span_id="span-1"))
            # Same trace_id string, different tenant -> must NOT be returned.
            other_tenant = await repo.create_span(
                _span(id="s4", tenant_id="other-tenant", trace_id="trace-x", span_id="span-1")
            )

            results = await repo.list_spans_for_trace("acme", "trace-x")
            result_ids = {r.id for r in results}

            # A real two-predicate WHERE (tenant_id AND trace_id) hitting exactly the
            # intended rows and no others — SQLite's small in-process fixtures can mask
            # a filter bug that a real Postgres query plan against a genuine composite
            # index (`ix_spans_tenant_trace`) won't.
            assert result_ids == {target1.id, target2.id}
            assert other_trace.id not in result_ids
            assert other_tenant.id not in result_ids
    finally:
        await engine.dispose()


async def test_list_traces_for_tenant_distinct_and_workflow_type_filter(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyObservabilityRepository(session)

            # Three spans in the same trace, same workflow_type -> DISTINCT must
            # collapse them to one (trace_id, workflow_type) row, not three.
            await repo.create_span(_span(id="w1", trace_id="trace-approval", span_id="s1", workflow_type="approval"))
            await repo.create_span(
                _span(id="w2", trace_id="trace-approval", span_id="s2", parent_span_id="s1", workflow_type="approval")
            )
            await repo.create_span(
                _span(id="w3", trace_id="trace-approval", span_id="s3", parent_span_id="s1", workflow_type="approval")
            )
            # A different trace under a different workflow_type -> must be excluded
            # when filtering to "approval".
            await repo.create_span(_span(id="w4", trace_id="trace-ingest", span_id="s1", workflow_type="ingest"))

            all_traces = await repo.list_traces_for_tenant("acme")
            assert ("trace-approval", "approval") in all_traces
            assert ("trace-ingest", "ingest") in all_traces
            # No duplicate row for trace-approval despite three spans sharing it.
            assert all_traces.count(("trace-approval", "approval")) == 1

            approval_only = await repo.list_traces_for_tenant("acme", workflow_type="approval")
            assert approval_only == [("trace-approval", "approval")]
    finally:
        await engine.dispose()
