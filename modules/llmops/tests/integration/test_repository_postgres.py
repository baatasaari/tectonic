"""Integration tier: proves things SQLite's unit-tier fakes can't reliably
prove -- the real `get_active_deployment` query (exactly one row, scoped
by tenant/model_name/target/stage) and status transitions round-tripping
through real Postgres. See `conftest.py` for how the Postgres instance is
obtained.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from llmops.core.domain import (
    DeploymentRecord,
    DeploymentStage,
    ModelVersionRecord,
    ModelVersionStatus,
    new_id,
)
from llmops.db.repository import SQLAlchemyLLMOpsRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["LLMOPS_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_get_active_deployment_returns_only_the_matching_active_row(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyLLMOpsRepository(session)
            v1 = await repo.create_model_version(
                ModelVersionRecord(id=new_id(), tenant_id="acme", model_name="chat-default", version="1", artifact_ref="a")
            )
            v2 = await repo.create_model_version(
                ModelVersionRecord(id=new_id(), tenant_id="acme", model_name="chat-default", version="2", artifact_ref="b")
            )
            # A superseded deployment for the same target -- must not be returned as active.
            await repo.create_deployment(
                DeploymentRecord(
                    id=new_id(), tenant_id="acme", model_version_id=v1.id, model_name="chat-default", target="prod",
                    stage=DeploymentStage.SUPERSEDED,
                )
            )
            active = await repo.create_deployment(
                DeploymentRecord(
                    id=new_id(), tenant_id="acme", model_version_id=v2.id, model_name="chat-default", target="prod",
                    stage=DeploymentStage.ACTIVE,
                )
            )
            # A different target -- must not be returned either.
            await repo.create_deployment(
                DeploymentRecord(
                    id=new_id(), tenant_id="acme", model_version_id=v2.id, model_name="chat-default", target="staging",
                    stage=DeploymentStage.ACTIVE,
                )
            )

            found = await repo.get_active_deployment(tenant_id="acme", model_name="chat-default", target="prod")

            assert found is not None
            assert found.id == active.id
    finally:
        await engine.dispose()


async def test_deployment_status_transitions_round_trip(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyLLMOpsRepository(session)
            version = await repo.create_model_version(
                ModelVersionRecord(id=new_id(), tenant_id="acme", model_name="m", version="1", artifact_ref="a")
            )
            deployment = await repo.create_deployment(
                DeploymentRecord(
                    id=new_id(), tenant_id="acme", model_version_id=version.id, model_name="m", target="prod",
                )
            )

            deployment.stage = DeploymentStage.ROLLED_BACK
            deployment.rollback_reason = "regression"
            updated = await repo.update_deployment(deployment)

            fetched = await repo.get_deployment(deployment.id)
            assert fetched.stage == DeploymentStage.ROLLED_BACK
            assert fetched.rollback_reason == "regression"
            assert updated.rollback_reason == "regression"

            version.status = ModelVersionStatus.ROLLED_BACK
            updated_version = await repo.update_model_version(version)
            assert updated_version.status == ModelVersionStatus.ROLLED_BACK
    finally:
        await engine.dispose()


async def test_list_model_versions_orders_newest_first_and_paginates(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyLLMOpsRepository(session)
            for i in range(5):
                await repo.create_model_version(
                    ModelVersionRecord(id=new_id(), tenant_id="page-tenant", model_name="m", version=str(i), artifact_ref="a")
                )

            page1, total1 = await repo.list_model_versions(tenant_id="page-tenant", limit=2, offset=0)
            page2, total2 = await repo.list_model_versions(tenant_id="page-tenant", limit=2, offset=2)

            assert total1 == total2 == 5
            assert len(page1) == 2
            assert len(page2) == 2
            assert {v.id for v in page1}.isdisjoint({v.id for v in page2})
    finally:
        await engine.dispose()
