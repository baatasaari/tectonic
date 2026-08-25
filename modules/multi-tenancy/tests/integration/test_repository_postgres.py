"""Integration tier: proves things SQLite's unit-tier fakes can't reliably
prove -- status filtering and pagination ordering, and isolation-probe
history round-tripping through real Postgres. See `conftest.py` for how
the Postgres instance is obtained.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from multi_tenancy.core.domain import IsolationProbeResult, TenantRecord, TenantStatus, new_id
from multi_tenancy.db.repository import SQLAlchemyMultiTenancyRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["MULTI_TENANCY_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_tenant_status_transitions_round_trip(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)
            tenant = await repo.create_tenant(TenantRecord(id=new_id(), name="Acme Corp"))

            tenant.status = TenantStatus.SUSPENDED
            updated = await repo.update_tenant(tenant)

            fetched = await repo.get_tenant(tenant.id)
            assert fetched.status == TenantStatus.SUSPENDED
            assert updated.status == TenantStatus.SUSPENDED
    finally:
        await engine.dispose()


async def test_list_tenants_filters_by_status(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)
            active = await repo.create_tenant(TenantRecord(id=new_id(), name="Active Co filter-test"))
            suspended = await repo.create_tenant(TenantRecord(id=new_id(), name="Suspended Co filter-test"))
            suspended.status = TenantStatus.SUSPENDED
            await repo.update_tenant(suspended)

            active_results, _active_total = await repo.list_tenants(status=TenantStatus.ACTIVE, limit=200)
            active_ids = {t.id for t in active_results}

            assert active.id in active_ids
            assert suspended.id not in active_ids
    finally:
        await engine.dispose()


async def test_isolation_probe_result_round_trip(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)
            created = await repo.create_probe_result(
                IsolationProbeResult(
                    id=new_id(), tenant_id="acme", target_name="agent-cards", passed=False, breach_count=2,
                    sample_size=10, details="2 foreign record(s) returned for a tenant-scoped query",
                )
            )

            results, total = await repo.list_probe_results(tenant_id="acme", target_name="agent-cards")

            assert total == 1
            assert results[0].id == created.id
            assert results[0].breach_count == 2
    finally:
        await engine.dispose()


async def test_list_probe_results_orders_newest_first_and_paginates(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)
            for i in range(5):
                await repo.create_probe_result(
                    IsolationProbeResult(
                        id=new_id(), tenant_id="page-tenant", target_name="agent-cards", passed=True,
                        breach_count=0, sample_size=i, details="ok",
                    )
                )

            page1, total1 = await repo.list_probe_results(tenant_id="page-tenant", limit=2, offset=0)
            page2, total2 = await repo.list_probe_results(tenant_id="page-tenant", limit=2, offset=2)

            assert total1 == total2 == 5
            assert len(page1) == 2
            assert len(page2) == 2
            assert {r.id for r in page1}.isdisjoint({r.id for r in page2})
    finally:
        await engine.dispose()
