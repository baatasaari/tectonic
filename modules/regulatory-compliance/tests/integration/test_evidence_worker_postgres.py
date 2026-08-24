"""Integration tier: the one property of the durable evidence-pack worker
that neither SQLite nor the in-memory fake can prove for real — that
`SELECT ... FOR UPDATE SKIP LOCKED` genuinely lets multiple concurrent
worker processes claim from the same table without ever double-claiming a
row, and without one blocking on another's held lock. See
`conftest.py` for how the Postgres instance is obtained.
"""
from __future__ import annotations

import asyncio
import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from regulatory_compliance.core.domain import EvidencePackRecord, EvidencePackStatus, new_id
from regulatory_compliance.db.repository import SQLAlchemyRegulatoryComplianceRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["REGULATORY_COMPLIANCE_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


@pytest.fixture(autouse=True)
async def _empty_evidence_packs_table(migrated_url):
    """claim_next_evidence_pack scans across all tenants by design (a real worker
    claims whatever's oldest and pending, platform-wide) -- so, unlike the other
    tests in this repository, these tests can't isolate themselves from each other
    with a distinct tenant_id alone. migrated_url is module-scoped (one DB, reused
    across every test in this file for speed); this resets its data, not its
    schema, before each test so no test's leftover unclaimed rows leak into the
    next one's assertions."""
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("DELETE FROM evidence_packs"))
            await conn.commit()
    finally:
        await engine.dispose()


async def test_concurrent_claims_never_double_claim_the_same_row(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        # Seed 8 pending packs, all claimable, via their own short-lived session.
        pack_ids: list[str] = []
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyRegulatoryComplianceRepository(session)
            for _ in range(8):
                pack = await repo.create_evidence_pack(
                    EvidencePackRecord(
                        id=new_id(), tenant_id="acme", framework_name="eu_ai_act",
                        status=EvidencePackStatus.GENERATING,
                    )
                )
                pack_ids.append(pack.id)

        # 4 "workers", each its own connection/session/transaction, claim concurrently.
        # If FOR UPDATE SKIP LOCKED weren't doing its job, two of these could return the
        # same row, or one could block waiting on another's lock instead of skipping it.
        async def claim_one(worker_id: str) -> str | None:
            async with engine.connect() as conn, AsyncSession(conn) as session:
                repo = SQLAlchemyRegulatoryComplianceRepository(session)
                claimed = await repo.claim_next_evidence_pack(worker_id, lease_seconds=120)
                return claimed.id if claimed else None

        results = await asyncio.gather(*(claim_one(f"worker-{i}") for i in range(4)))

        assert all(r is not None for r in results)
        # No two concurrent claimants ever got the same row.
        assert len(set(results)) == 4
        assert set(results) <= set(pack_ids)

        # The 4 claimed rows are no longer claimable by a fifth, immediate claim attempt
        # (their leases are still active); the 4 still-pending rows are.
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyRegulatoryComplianceRepository(session)
            fifth = await repo.claim_next_evidence_pack("worker-4", lease_seconds=120)
            assert fifth is not None
            assert fifth.id not in results
    finally:
        await engine.dispose()


async def test_a_claim_with_active_lease_is_invisible_to_a_concurrent_claimer(migrated_url):
    """The specific correctness property FOR UPDATE SKIP LOCKED gives: a second,
    fully concurrent claim attempt against the *only* pending row must come back
    empty, not block waiting for the first transaction's lock to release."""
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyRegulatoryComplianceRepository(session)
            pack = await repo.create_evidence_pack(
                EvidencePackRecord(
                    id=new_id(), tenant_id="acme", framework_name="eu_ai_act",
                    status=EvidencePackStatus.GENERATING,
                )
            )

        async def claim(worker_id: str) -> str | None:
            async with engine.connect() as conn, AsyncSession(conn) as session:
                repo = SQLAlchemyRegulatoryComplianceRepository(session)
                claimed = await repo.claim_next_evidence_pack(worker_id, lease_seconds=120)
                return claimed.id if claimed else None

        first, second = await asyncio.gather(claim("worker-a"), claim("worker-b"))

        assert {first, second} == {pack.id, None}
    finally:
        await engine.dispose()


async def test_force_expire_stale_leases_makes_an_in_flight_row_reclaimable(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyRegulatoryComplianceRepository(session)
            pack = await repo.create_evidence_pack(
                EvidencePackRecord(
                    id=new_id(), tenant_id="acme", framework_name="eu_ai_act",
                    status=EvidencePackStatus.GENERATING,
                )
            )
            claimed = await repo.claim_next_evidence_pack("dead-worker", lease_seconds=3600)
            assert claimed.id == pack.id

            # A fresh claim attempt right now must find nothing -- the lease is a full
            # hour out.
            immediate = await repo.claim_next_evidence_pack("worker-b", lease_seconds=120)
            assert immediate is None

            recovered = await repo.force_expire_stale_leases()
            assert recovered == 1

            reclaimed = await repo.claim_next_evidence_pack("worker-c", lease_seconds=120)
            assert reclaimed is not None
            assert reclaimed.id == pack.id
            assert reclaimed.attempts == 2  # claimed once by dead-worker, once by worker-c
    finally:
        await engine.dispose()
