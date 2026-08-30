"""Integration tier: the one property of the durable event-outbox worker
that neither SQLite nor the in-memory fake can prove for real -- that
`SELECT ... FOR UPDATE SKIP LOCKED` genuinely lets multiple concurrent
worker processes claim from the same table without ever double-claiming
a row, and without one blocking on another's held lock. This module's
rollout of Workflow Engine's own `test_outbox_worker_postgres.py`
(Module 1) to a second module's `event_outbox`. See `conftest.py` for
how the Postgres instance is obtained.
"""
from __future__ import annotations

import asyncio
import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from multi_tenancy.core import events
from multi_tenancy.core.domain import TenantRecord, TenantStatus, new_id
from multi_tenancy.db.repository import SQLAlchemyMultiTenancyRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["MULTI_TENANCY_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


@pytest.fixture(autouse=True)
async def _empty_tables(migrated_url):
    """claim_next_outbox_event scans across all tenants by design (a real
    worker claims whatever's oldest and pending, platform-wide) -- so,
    like Workflow Engine's own equivalent fixture, these tests can't
    isolate themselves from each other with a distinct tenant_id alone.
    migrated_url is module-scoped (one DB, reused across every test in
    this file for speed); this resets its data, not its schema, before
    each test."""
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("DELETE FROM event_outbox"))
            await conn.execute(text("DELETE FROM tenants"))
            await conn.commit()
    finally:
        await engine.dispose()


async def _seed_tenant(repo) -> TenantRecord:
    return await repo.create_tenant(TenantRecord(id=new_id(), name="Acme Corp"))


async def test_create_tenant_and_enqueue_event_commits_both_writes_atomically(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)
            tenant = TenantRecord(id=new_id(), name="Acme Corp", tier="enterprise")
            envelope = events.tenant_registered(tenant.id, tenant.name, tenant.tier, tenant.organisation_id)

            result = await repo.create_tenant_and_enqueue_event(
                tenant, topic=events.TOPIC_TENANT, envelope=envelope,
            )

            assert result.id == tenant.id

            fetched = await repo.get_tenant(tenant.id)
            assert fetched is not None

            claimed = await repo.claim_next_outbox_event("worker-a", lease_seconds=60)
            assert claimed is not None
            assert claimed.id == envelope["id"]
            assert claimed.topic == events.TOPIC_TENANT
            assert claimed.envelope == envelope  # a real JSONB round trip of the whole envelope
    finally:
        await engine.dispose()


async def test_update_tenant_and_enqueue_event_commits_both_writes_atomically(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)
            tenant = await _seed_tenant(repo)

            from dataclasses import replace as dc_replace

            updated_tenant = dc_replace(tenant, status=TenantStatus.SUSPENDED)
            envelope = events.tenant_status_changed(tenant.id, "active", "suspended")
            result = await repo.update_tenant_and_enqueue_event(
                updated_tenant, topic=events.TOPIC_TENANT, envelope=envelope,
            )

            assert result.status == TenantStatus.SUSPENDED

            claimed = await repo.claim_next_outbox_event("worker-a", lease_seconds=60)
            assert claimed is not None
            assert claimed.id == envelope["id"]
    finally:
        await engine.dispose()


async def test_concurrent_claims_never_double_claim_the_same_row(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        event_ids: list[str] = []
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)
            for _ in range(8):
                tenant = TenantRecord(id=new_id(), name="Acme Corp")
                envelope = events.tenant_registered(tenant.id, tenant.name, tenant.tier, tenant.organisation_id)
                await repo.create_tenant_and_enqueue_event(tenant, topic=events.TOPIC_TENANT, envelope=envelope)
                event_ids.append(envelope["id"])

        async def claim_one(worker_id: str) -> str | None:
            async with engine.connect() as conn, AsyncSession(conn) as session:
                repo = SQLAlchemyMultiTenancyRepository(session)
                claimed = await repo.claim_next_outbox_event(worker_id, lease_seconds=120)
                return claimed.id if claimed else None

        results = await asyncio.gather(*(claim_one(f"worker-{i}") for i in range(4)))

        assert all(r is not None for r in results)
        assert len(set(results)) == 4
        assert set(results) <= set(event_ids)
    finally:
        await engine.dispose()


async def test_a_claim_with_active_lease_is_invisible_to_a_concurrent_claimer(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)
            tenant = TenantRecord(id=new_id(), name="Acme Corp")
            envelope = events.tenant_registered(tenant.id, tenant.name, tenant.tier, tenant.organisation_id)
            await repo.create_tenant_and_enqueue_event(tenant, topic=events.TOPIC_TENANT, envelope=envelope)

        async def claim(worker_id: str) -> str | None:
            async with engine.connect() as conn, AsyncSession(conn) as session:
                repo = SQLAlchemyMultiTenancyRepository(session)
                claimed = await repo.claim_next_outbox_event(worker_id, lease_seconds=120)
                return claimed.id if claimed else None

        first, second = await asyncio.gather(claim("worker-a"), claim("worker-b"))

        assert {first, second} == {envelope["id"], None}
    finally:
        await engine.dispose()


async def test_force_expire_stale_leases_makes_an_in_flight_row_reclaimable(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)
            tenant = TenantRecord(id=new_id(), name="Acme Corp")
            envelope = events.tenant_registered(tenant.id, tenant.name, tenant.tier, tenant.organisation_id)
            await repo.create_tenant_and_enqueue_event(tenant, topic=events.TOPIC_TENANT, envelope=envelope)

            claimed = await repo.claim_next_outbox_event("dead-worker", lease_seconds=3600)
            assert claimed.id == envelope["id"]

            immediate = await repo.claim_next_outbox_event("worker-b", lease_seconds=120)
            assert immediate is None

            recovered = await repo.force_expire_stale_outbox_leases()
            assert recovered == 1

            reclaimed = await repo.claim_next_outbox_event("worker-c", lease_seconds=120)
            assert reclaimed is not None
            assert reclaimed.id == envelope["id"]
            assert reclaimed.attempts == 2
    finally:
        await engine.dispose()


async def test_mark_published_and_fail_exhausted_transitions(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMultiTenancyRepository(session)
            tenant_a = TenantRecord(id=new_id(), name="Acme Corp A")
            envelope_a = events.tenant_registered(tenant_a.id, tenant_a.name, tenant_a.tier, tenant_a.organisation_id)
            await repo.create_tenant_and_enqueue_event(tenant_a, topic=events.TOPIC_TENANT, envelope=envelope_a)

            tenant_b = TenantRecord(id=new_id(), name="Acme Corp B")
            envelope_b = events.tenant_registered(tenant_b.id, tenant_b.name, tenant_b.tier, tenant_b.organisation_id)
            await repo.create_tenant_and_enqueue_event(tenant_b, topic=events.TOPIC_TENANT, envelope=envelope_b)

            claimed_a = await repo.claim_next_outbox_event("worker-a", lease_seconds=60)
            await repo.mark_outbox_event_published(claimed_a.id)

            claimed_b = await repo.claim_next_outbox_event("worker-b", lease_seconds=60)
            for _ in range(4):
                await repo.requeue_outbox_event_for_retry(claimed_b.id, error="still failing")
                await repo.claim_next_outbox_event("worker-b", lease_seconds=0)
            failed_count = await repo.fail_exhausted_outbox_events(max_attempts=5)

            assert failed_count == 1
            still_pending = await repo.claim_next_outbox_event("worker-c", lease_seconds=60)
            assert still_pending is None  # the exhausted one is FAILED, not claimable anymore
    finally:
        await engine.dispose()
