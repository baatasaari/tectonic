"""Integration tier for the trace query, SLO, and alerting surfaces
(Phase 1 kernel): the real Postgres `GROUP BY`/`bool_or` aggregate query
behind `list_trace_summaries`, and real round-trips for the new
SLO/AlertRule/AlertEvent tables -- none of which SQLite's unit-tier
fakes can reliably prove. See `conftest.py` for how the Postgres
instance is obtained.
"""
from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from observability.core.domain import (
    AlertComparison,
    AlertEvent,
    AlertRule,
    AlertStatus,
    SLODefinition,
    SLOMetric,
    SpanRecord,
    new_id,
)
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
        "id": new_id(), "tenant_id": "acme", "trace_id": "trace-1", "span_id": "span-1", "parent_span_id": None,
        "name": "step", "service_name": "workflow-engine", "start_time": start,
        "end_time": start + timedelta(milliseconds=250), "ingested_at": start,
    }
    defaults.update(overrides)
    return SpanRecord(**defaults)


async def test_list_trace_summaries_real_aggregate_query(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyObservabilityRepository(session)
            tenant = f"tenant-{new_id()[:8]}"
            trace = f"trace-{new_id()[:8]}"
            start = datetime.now(UTC)
            await repo.create_span(_span(
                tenant_id=tenant, trace_id=trace, span_id="s1", start_time=start,
                end_time=start + timedelta(seconds=1), status="ok", workflow_type="onboarding",
            ))
            await repo.create_span(_span(
                tenant_id=tenant, trace_id=trace, span_id="s2", start_time=start + timedelta(seconds=1),
                end_time=start + timedelta(seconds=3), status="error", workflow_type="onboarding",
            ))
            # A second, unrelated trace for the same tenant -- must not get merged in.
            await repo.create_span(_span(tenant_id=tenant, trace_id=f"{trace}-other", span_id="s1"))

            summaries, total = await repo.list_trace_summaries(tenant)

            assert total == 2
            this_trace = next(s for s in summaries if s.trace_id == trace)
            assert this_trace.span_count == 2
            assert this_trace.has_error is True
            assert this_trace.duration_seconds == pytest.approx(3.0)
    finally:
        await engine.dispose()


async def test_list_trace_summaries_filters_by_workflow_type(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyObservabilityRepository(session)
            tenant = f"tenant-{new_id()[:8]}"
            await repo.create_span(_span(tenant_id=tenant, trace_id="t1", workflow_type="onboarding"))
            await repo.create_span(_span(tenant_id=tenant, trace_id="t2", workflow_type="checkout"))

            summaries, total = await repo.list_trace_summaries(tenant, workflow_type="checkout")

            assert total == 1
            assert summaries[0].trace_id == "t2"
    finally:
        await engine.dispose()


async def test_list_spans_in_window_filters_by_start_time_and_service(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyObservabilityRepository(session)
            tenant = f"tenant-{new_id()[:8]}"
            now = datetime.now(UTC)
            await repo.create_span(_span(
                tenant_id=tenant, trace_id="t1", service_name="llm-gateway", start_time=now - timedelta(hours=2),
                end_time=now - timedelta(hours=2),
            ))
            recent = await repo.create_span(_span(
                tenant_id=tenant, trace_id="t2", service_name="llm-gateway", start_time=now, end_time=now,
            ))
            await repo.create_span(_span(
                tenant_id=tenant, trace_id="t3", service_name="workflow-engine", start_time=now, end_time=now,
            ))

            spans = await repo.list_spans_in_window(tenant, service_name="llm-gateway", since=now - timedelta(hours=1))

            assert [s.id for s in spans] == [recent.id]
    finally:
        await engine.dispose()


async def test_slo_round_trips_through_real_postgres(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyObservabilityRepository(session)
            created = await repo.create_slo(SLODefinition(
                id=new_id(), tenant_id="acme", name="Error budget", metric=SLOMetric.ERROR_RATE, target=0.05,
                window_hours=24, service_name="llm-gateway",
            ))

            fetched = await repo.get_slo(created.id)
            assert fetched.metric == SLOMetric.ERROR_RATE
            assert fetched.target == 0.05
            assert fetched.service_name == "llm-gateway"
    finally:
        await engine.dispose()


async def test_alert_rule_and_event_lifecycle_round_trips(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyObservabilityRepository(session)
            rule = await repo.create_alert_rule(AlertRule(
                id=new_id(), tenant_id="acme", name="High latency", metric=SLOMetric.LATENCY_P95,
                comparison=AlertComparison.GT, threshold=2.0, window_hours=1,
            ))

            assert await repo.get_latest_alert_event(rule.id) is None

            firing = await repo.create_alert_event(AlertEvent(
                id=new_id(), rule_id=rule.id, tenant_id="acme", status=AlertStatus.FIRING, value=3.5, threshold=2.0,
            ))
            latest = await repo.get_latest_alert_event(rule.id)
            assert latest.id == firing.id
            assert latest.status == AlertStatus.FIRING

            firing.status = AlertStatus.RESOLVED
            firing.resolved_at = datetime.now(UTC)
            resolved = await repo.update_alert_event(firing)
            assert resolved.status == AlertStatus.RESOLVED
            assert resolved.resolved_at is not None

            events, total = await repo.list_alert_events(tenant_id="acme", status=AlertStatus.RESOLVED)
            assert total == 1
            assert events[0].id == firing.id

            disabled = replace(rule, enabled=False)
            updated_rule = await repo.update_alert_rule(disabled)
            assert updated_rule.enabled is False
    finally:
        await engine.dispose()
