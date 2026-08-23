"""Integration tier (LLD's own testing plan): the SQLAlchemy repository
against a real Postgres — not part of the default unit-test run. See
`conftest.py` for how the Postgres instance is obtained.

Specifically exercises what SQLite's unit-tier tests can't: real JSONB
list round-tripping with exact order preserved (`EvalRun.metrics_evaluated`),
a real UUID primary key round trip through `get_eval_run`, real JSONB dict
round-tripping that keeps float values as floats rather than silently
stringifying them (`DomainMetricPack.custom_thresholds`), and a multi-row
filtered query (`list_metric_scores_for_tenant`) that must hit only the
rows matching both tenant *and* agent_ref, not every row for the tenant.
"""
from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from evaluation_framework.core.domain import (
    DomainMetricPackRecord,
    EvalRunRecord,
    GateResultRecord,
    MetricScoreRecord,
    new_id,
)
from evaluation_framework.db.repository import SQLAlchemyEvaluationFrameworkRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["EVALUATION_FRAMEWORK_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_eval_run_metrics_evaluated_round_trips_as_real_jsonb_with_uuid_pk(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyEvaluationFrameworkRepository(session)
            metrics = ["faithfulness", "coherence", "tool_trace_correctness", "faithfulness"]
            record = EvalRunRecord(
                id=new_id(), tenant_id="acme", trigger_source="ci_cd", agent_ref="agent-1",
                metrics_evaluated=metrics,
            )
            created = await repo.create_eval_run(record)
            # A real JSONB round trip preserves list order (including the duplicate
            # entry) exactly — SQLite's JSON-as-TEXT variant can silently get away
            # with reordering or deduplicating in ways Postgres's native JSONB won't.
            assert created.metrics_evaluated == metrics

            # A real UUID (asyncpg returns/accepts a genuine UUID type; SQLite's CHAR(36)
            # variant just stores it as a plain string) — confirm it round-trips as a
            # fetchable primary key, not just a string that happens to look like one.
            fetched = await repo.get_eval_run("acme", created.id)
            assert fetched is not None
            assert fetched.id == created.id
            assert fetched.metrics_evaluated == metrics
    finally:
        await engine.dispose()


async def test_domain_metric_pack_custom_thresholds_preserve_float_types(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyEvaluationFrameworkRepository(session)
            thresholds = {"faithfulness": 0.9, "coherence": 0.75, "guaranteed_return_flag": 0.0}
            created = await repo.create_domain_pack(
                DomainMetricPackRecord(
                    id=new_id(), tenant_id="acme", pack_name="financial_guidance",
                    custom_thresholds=thresholds,
                )
            )
            # Real JSONB keeps numeric values as genuine floats (including 0.0, which
            # a naive text/JSON-as-string round trip could coerce to an int or a
            # string) — confirm both the values and their types survive exactly.
            assert created.custom_thresholds == thresholds
            for value in created.custom_thresholds.values():
                assert isinstance(value, float)

            [fetched] = await repo.list_domain_packs("acme")
            assert fetched.custom_thresholds == thresholds
    finally:
        await engine.dispose()


async def test_list_metric_scores_for_tenant_filters_to_only_matching_rows(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyEvaluationFrameworkRepository(session)
            run = await repo.create_eval_run(
                EvalRunRecord(id=new_id(), tenant_id="tenant-a", trigger_source="ci_cd", agent_ref="agent-1")
            )

            matching = await repo.create_metric_score(
                MetricScoreRecord(
                    id=new_id(), eval_run_id=run.id, tenant_id="tenant-a", agent_ref="agent-1",
                    metric_name="faithfulness", score=0.92, threshold=0.8, passed=True,
                )
            )
            # Same tenant, different agent -> must NOT be returned when filtering by agent_ref.
            other_agent = await repo.create_metric_score(
                MetricScoreRecord(
                    id=new_id(), eval_run_id=run.id, tenant_id="tenant-a", agent_ref="agent-2",
                    metric_name="faithfulness", score=0.61, threshold=0.8, passed=False,
                )
            )
            # Different tenant, same agent name -> must NOT be returned either.
            other_tenant = await repo.create_metric_score(
                MetricScoreRecord(
                    id=new_id(), eval_run_id=run.id, tenant_id="tenant-b", agent_ref="agent-1",
                    metric_name="faithfulness", score=0.55, threshold=0.8, passed=False,
                )
            )

            results = await repo.list_metric_scores_for_tenant("tenant-a", agent_ref="agent-1")
            result_ids = {r.id for r in results}

            # A real multi-predicate WHERE (tenant_id AND agent_ref) hitting exactly the
            # intended row and no others — SQLite's looser type affinity and small test
            # fixtures can mask a filter bug that a real Postgres query plan won't.
            assert result_ids == {matching.id}
            assert other_agent.id not in result_ids
            assert other_tenant.id not in result_ids

            # Filtering by tenant alone should surface both of that tenant's rows.
            tenant_only = await repo.list_metric_scores_for_tenant("tenant-a")
            assert {r.id for r in tenant_only} == {matching.id, other_agent.id}
    finally:
        await engine.dispose()


async def test_gate_result_blocking_failures_round_trip_as_real_jsonb(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyEvaluationFrameworkRepository(session)
            run = await repo.create_eval_run(
                EvalRunRecord(id=new_id(), tenant_id="acme", trigger_source="ci_cd", agent_ref="agent-1")
            )
            failures = ["faithfulness", "tool_trace_correctness"]
            gate = await repo.create_gate_result(
                GateResultRecord(
                    id=new_id(), eval_run_id=run.id, overall_passed=False,
                    blocking_failures=failures, environment="production",
                )
            )
            assert gate.blocking_failures == failures
            assert gate.overall_passed is False
    finally:
        await engine.dispose()
