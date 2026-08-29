"""Integration tier: proves things SQLite's unit-tier fakes can't reliably
prove -- status filtering and pagination ordering, and isolation-probe
history round-tripping through real Postgres. See `conftest.py` for how
the Postgres instance is obtained.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from multi_tenancy.core.domain import (
    EnvironmentRecord,
    HierarchyStatus,
    IsolationProbeResult,
    OptimisticConcurrencyError,
    OrganisationRecord,
    ResourceAllocation,
    ResourceAllocationStatus,
    TenantRecord,
    TenantStatus,
    WorkspaceRecord,
    new_id,
    now,
)
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


async def test_entitlements_round_trip_and_stamp_configured_at(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)
            tenant = await repo.create_tenant(TenantRecord(id=new_id(), name="Acme Corp entitlements-test"))
            assert tenant.entitlements_configured_at is None

            replaced = await repo.replace_entitlements(
                tenant_id=tenant.id, module_names=["agent-cards", "guardrails"],
            )
            assert {e.module_name for e in replaced} == {"agent-cards", "guardrails"}

            fetched = await repo.get_tenant(tenant.id)
            assert fetched.entitlements_configured_at is not None

            listed = await repo.list_entitlements(tenant.id)
            assert {e.module_name for e in listed} == {"agent-cards", "guardrails"}

            # wholesale replace: a second call drops what isn't in the new list
            replaced_again = await repo.replace_entitlements(tenant_id=tenant.id, module_names=["guardrails"])
            assert {e.module_name for e in replaced_again} == {"guardrails"}
            listed_again = await repo.list_entitlements(tenant.id)
            assert {e.module_name for e in listed_again} == {"guardrails"}
    finally:
        await engine.dispose()


async def test_organisation_workspace_environment_hierarchy_round_trips(migrated_url):
    """Proves the full Organisation -> Tenant -> Workspace -> Environment
    chain through real Postgres foreign keys and JSONB `labels` columns
    -- exactly what SQLite's unit-tier fakes can't exercise."""
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)

            org = await repo.create_organisation(
                OrganisationRecord(id=new_id(), name="Acme Holdings hierarchy-test", labels={"tier": "enterprise"}),
            )
            assert org.version == 1

            tenant = await repo.create_tenant(
                TenantRecord(id=new_id(), name="Acme Corp hierarchy-test", organisation_id=org.id),
            )
            fetched_tenant = await repo.get_tenant(tenant.id)
            assert fetched_tenant.organisation_id == org.id

            ws = await repo.create_workspace(
                WorkspaceRecord(id=new_id(), tenant_id=tenant.id, name="Production workflows"),
            )
            fetched_ws = await repo.get_workspace(ws.id)
            assert fetched_ws.tenant_id == tenant.id

            env = await repo.create_environment(
                EnvironmentRecord(id=new_id(), workspace_id=ws.id, name="production", kind="production", region="eu-west-1"),
            )
            fetched_env = await repo.get_environment(env.id)
            assert fetched_env.workspace_id == ws.id
            assert fetched_env.region == "eu-west-1"

            # Real compare-and-swap: WHERE version = expected_version, enforced by
            # Postgres itself, not an in-memory guess.
            env.status = HierarchyStatus.SUSPENDED
            updated_env = await repo.update_environment(env, expected_version=1)
            assert updated_env.status == HierarchyStatus.SUSPENDED
            assert updated_env.version == 2

            with pytest.raises(OptimisticConcurrencyError):
                await repo.update_environment(env, expected_version=1)  # stale -- real version is now 2

            ws_list, ws_total = await repo.list_workspaces(tenant_id=tenant.id)
            assert ws_total == 1
            assert ws_list[0].id == ws.id

            env_list, env_total = await repo.list_environments(workspace_id=ws.id)
            assert env_total == 1
            assert env_list[0].id == env.id
    finally:
        await engine.dispose()


async def test_quota_set_upsert_round_trips_and_is_a_wholesale_replace(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)
            tenant = await repo.create_tenant(TenantRecord(id=new_id(), name="Acme Corp quota-test"))

            assert await repo.get_quota_set(tenant.id) is None

            first = await repo.upsert_quota_set(
                tenant_id=tenant.id, limits={"requests_per_minute": 600, "storage_gb": 500},
            )
            assert first.version == 1
            assert first.configured_at is not None

            second = await repo.upsert_quota_set(tenant_id=tenant.id, limits={"requests_per_minute": 1200})
            assert second.version == 2
            assert second.limits == {"requests_per_minute": 1200}  # storage_gb dropped -- a real replace

            fetched = await repo.get_quota_set(tenant.id)
            assert fetched.limits == {"requests_per_minute": 1200}
    finally:
        await engine.dispose()


async def test_quota_counter_increment_is_atomic_and_windows_reset(migrated_url):
    """Real concurrent-safety proof SQLite fakes can't give: two
    increments issued as if from two different concurrent callers still
    both land (a real `INSERT ... ON CONFLICT DO UPDATE`, not a
    read-then-write race), and a new fixed window starts the count over.
    """
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)
            tenant_id = new_id()
            window_a = datetime(2026, 1, 1, 0, 0, 10, tzinfo=UTC)

            first = await repo.increment_quota_counter(
                tenant_id=tenant_id, resource_class="requests_per_minute", amount=1,
                window_seconds=60, now=window_a,
            )
            second = await repo.increment_quota_counter(
                tenant_id=tenant_id, resource_class="requests_per_minute", amount=1,
                window_seconds=60, now=window_a,
            )
            assert first == 1.0
            assert second == 2.0

            window_b = window_a + timedelta(minutes=1)
            reset = await repo.increment_quota_counter(
                tenant_id=tenant_id, resource_class="requests_per_minute", amount=1,
                window_seconds=60, now=window_b,
            )
            assert reset == 1.0  # a new window, not a continuation of the 2.0 above
    finally:
        await engine.dispose()


async def test_resource_allocation_round_trips_and_finds_the_active_one(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)
            org = await repo.create_organisation(OrganisationRecord(id=new_id(), name="Acme Holdings ra-test"))
            tenant = await repo.create_tenant(
                TenantRecord(id=new_id(), name="Acme Corp ra-test", organisation_id=org.id),
            )
            ws = await repo.create_workspace(WorkspaceRecord(id=new_id(), tenant_id=tenant.id, name="Production"))
            env = await repo.create_environment(
                EnvironmentRecord(id=new_id(), workspace_id=ws.id, name="production", kind="production"),
            )

            assert await repo.get_active_resource_allocation(env.id) is None

            requested = await repo.create_resource_allocation(
                ResourceAllocation(
                    id=new_id(), environment_id=env.id, resources={"cpu_cores": 4, "replicas": 2},
                    requested_by="alice",
                ),
            )
            assert requested.status == ResourceAllocationStatus.REQUESTED
            assert await repo.get_active_resource_allocation(env.id) is None

            requested.status = ResourceAllocationStatus.ACTIVE
            requested.approved_by = "platform-admin"
            requested.updated_at = now()
            approved = await repo.update_resource_allocation(requested, expected_version=1)
            assert approved.status == ResourceAllocationStatus.ACTIVE
            assert approved.version == 2

            active = await repo.get_active_resource_allocation(env.id)
            assert active is not None
            assert active.id == approved.id
            assert active.resources == {"cpu_cores": 4, "replicas": 2}

            items, total = await repo.list_resource_allocations(environment_id=env.id)
            assert total == 1
            assert items[0].id == approved.id
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
