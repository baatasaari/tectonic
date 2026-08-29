"""Integration tier for real optimistic-concurrency enforcement: proves
the real `WHERE version = :expected_version` compare-and-swap resolves
a genuine race under real concurrent callers against real Postgres --
not just single-threaded dict logic, which SQLite's unit-tier fakes
can't exercise regardless of how carefully they mimic the check (see
`tests/unit/test_organisation_service.py`'s own repository-layer test
for why a race can't actually be *induced* against a synchronous fake).
"""
from __future__ import annotations

import asyncio
import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from multi_tenancy.core.domain import (
    EnvironmentRecord,
    HierarchyStatus,
    OptimisticConcurrencyError,
    OrganisationRecord,
    ResourceAllocation,
    ResourceAllocationStatus,
    TenantRecord,
    WorkspaceRecord,
    new_id,
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


async def test_ten_concurrent_organisation_suspends_exactly_one_wins(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)
            org = await repo.create_organisation(OrganisationRecord(id=new_id(), name="Acme Holdings occ-test"))
        assert org.version == 1

        async def suspend_once() -> str:
            async with engine.connect() as conn, AsyncSession(conn) as session:
                repo = SQLAlchemyMultiTenancyRepository(session)
                stale = await repo.get_organisation(org.id)
                stale.status = HierarchyStatus.SUSPENDED
                try:
                    await repo.update_organisation(stale, expected_version=1)
                    return "won"
                except OptimisticConcurrencyError:
                    return "conflict"

        results = await asyncio.gather(*(suspend_once() for _ in range(10)))

        # All ten callers read the same version=1 -- exactly one real compare-and-swap
        # can succeed against it; the other nine must each get a real conflict, never a
        # silently-overwritten decision.
        assert results.count("won") == 1
        assert results.count("conflict") == 9

        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)
            final = await repo.get_organisation(org.id)
        assert final.status == HierarchyStatus.SUSPENDED
        assert final.version == 2  # exactly one increment, not ten
    finally:
        await engine.dispose()


async def test_two_reviewers_racing_approve_and_reject_only_one_lands(migrated_url):
    """The real-world scenario this whole ticket exists for: two
    reviewers deciding on the same REQUESTED ResourceAllocation nearly
    simultaneously, one approving and one rejecting."""
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)
            org = await repo.create_organisation(OrganisationRecord(id=new_id(), name="Acme Holdings occ-test-2"))
            tenant = await repo.create_tenant(
                TenantRecord(id=new_id(), name="Acme Corp occ-test-2", organisation_id=org.id),
            )
            ws = await repo.create_workspace(WorkspaceRecord(id=new_id(), tenant_id=tenant.id, name="Production"))
            env = await repo.create_environment(
                EnvironmentRecord(id=new_id(), workspace_id=ws.id, name="production", kind="production"),
            )
            allocation = await repo.create_resource_allocation(
                ResourceAllocation(id=new_id(), environment_id=env.id, resources={"cpu_cores": 4}),
            )
        assert allocation.version == 1

        async def decide(approve: bool) -> str:
            async with engine.connect() as conn, AsyncSession(conn) as session:
                repo = SQLAlchemyMultiTenancyRepository(session)
                stale = await repo.get_resource_allocation(allocation.id)
                if approve:
                    stale.status = ResourceAllocationStatus.ACTIVE
                    stale.approved_by = "reviewer-a"
                else:
                    stale.status = ResourceAllocationStatus.REJECTED
                    stale.rejection_reason = "reviewer-b says no"
                try:
                    await repo.update_resource_allocation(stale, expected_version=1)
                    return "approved" if approve else "rejected"
                except OptimisticConcurrencyError:
                    return "conflict"

        results = await asyncio.gather(decide(True), decide(False))

        assert "conflict" in results  # exactly one of the two decisions landed
        assert results.count("conflict") == 1

        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)
            final = await repo.get_resource_allocation(allocation.id)
        assert final.status in (ResourceAllocationStatus.ACTIVE, ResourceAllocationStatus.REJECTED)
        assert final.version == 2  # exactly one decision landed, not both
    finally:
        await engine.dispose()
