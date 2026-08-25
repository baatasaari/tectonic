"""Integration tier: proves things SQLite's unit-tier fakes can't reliably
prove -- real aggregate SUM queries over usage_events with a time-window
filter, and budget-policy/optimisation-action round trips through real
Postgres. See `conftest.py` for how the Postgres instance is obtained.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from finops.core.domain import (
    BudgetPeriod,
    BudgetPolicyRecord,
    OptimisationActionRecord,
    UsageEventRecord,
    new_id,
)
from finops.db.repository import SQLAlchemyFinOpsRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["FINOPS_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_sum_usage_cost_filters_by_tenant_and_time_window(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyFinOpsRepository(session)
            now = datetime.now(UTC)

            # In window, right tenant -- counted.
            await repo.create_usage_event(
                UsageEventRecord(
                    id=new_id(), tenant_id="acme", source_module="vector-db", resource_type="storage-gb",
                    quantity=10, unit_cost=1.0, cost=10.0, occurred_at=now,
                )
            )
            # In window, wrong tenant -- not counted.
            await repo.create_usage_event(
                UsageEventRecord(
                    id=new_id(), tenant_id="other-tenant", source_module="vector-db", resource_type="storage-gb",
                    quantity=10, unit_cost=1.0, cost=999.0, occurred_at=now,
                )
            )
            # Right tenant, outside window -- not counted.
            await repo.create_usage_event(
                UsageEventRecord(
                    id=new_id(), tenant_id="acme", source_module="vector-db", resource_type="storage-gb",
                    quantity=10, unit_cost=1.0, cost=999.0, occurred_at=now - timedelta(days=60),
                )
            )

            total = await repo.sum_usage_cost(
                tenant_id="acme", start=now - timedelta(hours=1), end=now + timedelta(hours=1),
            )

            assert total == 10.0
    finally:
        await engine.dispose()


async def test_budget_policy_create_get_update_round_trip(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyFinOpsRepository(session)
            created = await repo.create_budget_policy(
                BudgetPolicyRecord(
                    id=new_id(), tenant_id="acme", period=BudgetPeriod.MONTHLY, limit_amount=1000.0,
                    alert_threshold_pct=0.8,
                )
            )

            fetched = await repo.get_budget_policy(created.id)
            assert fetched is not None
            assert fetched.limit_amount == 1000.0
            assert fetched.period == BudgetPeriod.MONTHLY

            fetched.alert_threshold_pct = 0.7
            updated = await repo.update_budget_policy(fetched)
            assert updated.alert_threshold_pct == 0.7

            refetched = await repo.get_budget_policy(created.id)
            assert refetched.alert_threshold_pct == 0.7
    finally:
        await engine.dispose()


async def test_get_budget_policy_returns_none_when_missing(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyFinOpsRepository(session)
            import uuid

            found = await repo.get_budget_policy(str(uuid.uuid4()))
            assert found is None
    finally:
        await engine.dispose()


async def test_list_optimisation_actions_orders_newest_first_and_paginates(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyFinOpsRepository(session)
            policy = await repo.create_budget_policy(
                BudgetPolicyRecord(
                    id=new_id(), tenant_id="acme", period=BudgetPeriod.MONTHLY, limit_amount=1000.0,
                )
            )
            base = datetime.now(UTC) - timedelta(minutes=10)
            for i in range(5):
                await repo.create_optimisation_action(
                    OptimisationActionRecord(
                        id=new_id(), tenant_id="acme", budget_policy_id=policy.id,
                        action_type="lowered_alert_threshold", previous_value=0.8 - i * 0.05,
                        new_value=0.75 - i * 0.05, reason=f"action {i}",
                        taken_at=base + timedelta(minutes=i),
                    )
                )
            # An action for a different policy -- must never appear in the results.
            other_policy = await repo.create_budget_policy(
                BudgetPolicyRecord(
                    id=new_id(), tenant_id="acme", period=BudgetPeriod.MONTHLY, limit_amount=500.0,
                )
            )
            await repo.create_optimisation_action(
                OptimisationActionRecord(
                    id=new_id(), tenant_id="acme", budget_policy_id=other_policy.id,
                    action_type="lowered_alert_threshold", previous_value=0.8, new_value=0.75, reason="other policy",
                )
            )

            page1, total1 = await repo.list_optimisation_actions(budget_policy_id=policy.id, limit=2, offset=0)
            page2, total2 = await repo.list_optimisation_actions(budget_policy_id=policy.id, limit=2, offset=2)

            assert total1 == total2 == 5
            assert len(page1) == 2
            assert len(page2) == 2
            assert {a.id for a in page1}.isdisjoint({a.id for a in page2})
            # newest first
            assert page1[0].taken_at > page1[1].taken_at
    finally:
        await engine.dispose()
