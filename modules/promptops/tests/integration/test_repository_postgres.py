"""Integration tier: proves things SQLite's unit-tier fakes can't reliably
prove -- the real `get_active_prompt_version` query (exactly one row,
scoped by tenant/prompt_name/status) and status transitions round-tripping
through real Postgres. See `conftest.py` for how the Postgres instance is
obtained.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from promptops.core.domain import (
    ABTestRecord,
    ABTestStatus,
    PromptVersionRecord,
    PromptVersionStatus,
    new_id,
)
from promptops.db.repository import SQLAlchemyPromptOpsRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["PROMPTOPS_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_get_active_prompt_version_returns_only_the_matching_active_row(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyPromptOpsRepository(session)
            # An archived version for the same prompt -- must not be returned as active.
            await repo.create_prompt_version(
                PromptVersionRecord(
                    id=new_id(), tenant_id="acme", prompt_name="claims-summariser", version="1", template="t1",
                    status=PromptVersionStatus.ARCHIVED,
                )
            )
            active = await repo.create_prompt_version(
                PromptVersionRecord(
                    id=new_id(), tenant_id="acme", prompt_name="claims-summariser", version="2", template="t2",
                    status=PromptVersionStatus.ACTIVE,
                )
            )
            # A different prompt_name -- must not be returned either.
            await repo.create_prompt_version(
                PromptVersionRecord(
                    id=new_id(), tenant_id="acme", prompt_name="other-prompt", version="1", template="t3",
                    status=PromptVersionStatus.ACTIVE,
                )
            )

            found = await repo.get_active_prompt_version(tenant_id="acme", prompt_name="claims-summariser")

            assert found is not None
            assert found.id == active.id
    finally:
        await engine.dispose()


async def test_prompt_version_status_transitions_round_trip(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyPromptOpsRepository(session)
            version = await repo.create_prompt_version(
                PromptVersionRecord(id=new_id(), tenant_id="acme", prompt_name="p", version="1", template="t")
            )

            version.status = PromptVersionStatus.ACTIVE
            version.promoted_pass_rate = 0.92
            version.promoted_sample_size = 25
            updated = await repo.update_prompt_version(version)

            fetched = await repo.get_prompt_version(version.id)
            assert fetched.status == PromptVersionStatus.ACTIVE
            assert fetched.promoted_pass_rate == 0.92
            assert fetched.promoted_sample_size == 25
            assert updated.promoted_pass_rate == 0.92
    finally:
        await engine.dispose()


async def test_ab_test_round_trip(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyPromptOpsRepository(session)
            a = await repo.create_prompt_version(
                PromptVersionRecord(id=new_id(), tenant_id="acme", prompt_name="p", version="1", template="t1")
            )
            b = await repo.create_prompt_version(
                PromptVersionRecord(id=new_id(), tenant_id="acme", prompt_name="p", version="2", template="t2")
            )
            ab_test = await repo.create_ab_test(
                ABTestRecord(id=new_id(), tenant_id="acme", prompt_name="p", version_a_id=a.id, version_b_id=b.id)
            )

            ab_test.status = ABTestStatus.CONCLUDED
            ab_test.winner_version_id = a.id
            ab_test.p_value = 0.01
            ab_test.sample_size_a = 20
            ab_test.sample_size_b = 20
            updated = await repo.update_ab_test(ab_test)

            fetched = await repo.get_ab_test(ab_test.id)
            assert fetched.status == ABTestStatus.CONCLUDED
            assert fetched.winner_version_id == a.id
            assert updated.p_value == 0.01
    finally:
        await engine.dispose()


async def test_list_prompt_versions_orders_newest_first_and_paginates(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyPromptOpsRepository(session)
            for i in range(5):
                await repo.create_prompt_version(
                    PromptVersionRecord(
                        id=new_id(), tenant_id="page-tenant", prompt_name="p", version=str(i), template="t",
                    )
                )

            page1, total1 = await repo.list_prompt_versions(tenant_id="page-tenant", limit=2, offset=0)
            page2, total2 = await repo.list_prompt_versions(tenant_id="page-tenant", limit=2, offset=2)

            assert total1 == total2 == 5
            assert len(page1) == 2
            assert len(page2) == 2
            assert {v.id for v in page1}.isdisjoint({v.id for v in page2})
    finally:
        await engine.dispose()
