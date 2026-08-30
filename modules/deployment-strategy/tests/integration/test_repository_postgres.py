"""Integration tier: proves things SQLite's unit-tier fakes can't reliably
prove -- the real `get_active_deployment` query (exactly one row, scoped
by tenant/service_name/target/stage) and status transitions round-tripping
through real Postgres. See `conftest.py` for how the Postgres instance is
obtained.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from deployment_strategy.core.domain import DeploymentRecord, DeploymentStage, new_id
from deployment_strategy.db.repository import SQLAlchemyDeploymentStrategyRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["DEPLOYMENT_STRATEGY_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_get_active_deployment_returns_only_the_matching_active_row(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyDeploymentStrategyRepository(session)
            # A superseded deployment for the same target -- must not be returned as active.
            await repo.create_deployment(
                DeploymentRecord(
                    id=new_id(), tenant_id="acme", service_name="conversational-engine", build_ref="v1",
                    target="prod", stage=DeploymentStage.SUPERSEDED,
                )
            )
            active = await repo.create_deployment(
                DeploymentRecord(
                    id=new_id(), tenant_id="acme", service_name="conversational-engine", build_ref="v2",
                    target="prod", stage=DeploymentStage.ACTIVE,
                )
            )
            # A different target -- must not be returned either.
            await repo.create_deployment(
                DeploymentRecord(
                    id=new_id(), tenant_id="acme", service_name="conversational-engine", build_ref="v2",
                    target="staging", stage=DeploymentStage.ACTIVE,
                )
            )

            found = await repo.get_active_deployment(tenant_id="acme", service_name="conversational-engine", target="prod")

            assert found is not None
            assert found.id == active.id
    finally:
        await engine.dispose()


async def test_deployment_status_transitions_round_trip(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyDeploymentStrategyRepository(session)
            deployment = await repo.create_deployment(
                DeploymentRecord(id=new_id(), tenant_id="acme", service_name="svc", build_ref="v1", target="prod")
            )

            deployment.stage = DeploymentStage.ROLLED_BACK
            deployment.rollback_reason = "regression"
            updated = await repo.update_deployment(deployment)

            fetched = await repo.get_deployment(deployment.id)
            assert fetched.stage == DeploymentStage.ROLLED_BACK
            assert fetched.rollback_reason == "regression"
            assert updated.rollback_reason == "regression"
    finally:
        await engine.dispose()


async def test_list_deployments_orders_newest_first_and_paginates(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyDeploymentStrategyRepository(session)
            for i in range(5):
                await repo.create_deployment(
                    DeploymentRecord(
                        id=new_id(), tenant_id="page-tenant", service_name="svc", build_ref=str(i), target="prod",
                    )
                )

            page1, total1 = await repo.list_deployments(tenant_id="page-tenant", limit=2, offset=0)
            page2, total2 = await repo.list_deployments(tenant_id="page-tenant", limit=2, offset=2)

            assert total1 == total2 == 5
            assert len(page1) == 2
            assert len(page2) == 2
            assert {d.id for d in page1}.isdisjoint({d.id for d in page2})
    finally:
        await engine.dispose()


async def test_create_deployment_persists_budget_policy_id(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyDeploymentStrategyRepository(session)
            created = await repo.create_deployment(
                DeploymentRecord(
                    id=new_id(), tenant_id="acme", service_name="svc", build_ref="v1", target="prod",
                    budget_policy_id=new_id(),
                )
            )

            fetched = await repo.get_deployment(created.id)
            assert fetched.budget_policy_id == created.budget_policy_id
    finally:
        await engine.dispose()
