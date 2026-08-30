"""Integration tier: the concurrency properties neither SQLite nor the
in-memory fake can prove for real.

1. `append_event`'s per-tenant `SELECT ... FOR UPDATE` genuinely
   serializes concurrent writers for the *same* tenant -- two concurrent
   ingests never produce the same sequence_number, and the resulting
   chain still verifies (proving the lock, not just the arithmetic, is
   what's doing the work).
2. `claim_next_audit_pack`'s `SELECT ... FOR UPDATE SKIP LOCKED` lets
   multiple worker processes claim from the same table without ever
   double-claiming a row -- the identical property Module 17's own
   evidence-pack worker integration tier already proves, reused here for
   the audit-pack queue.

See `conftest.py` for how the Postgres instance is obtained.
"""
from __future__ import annotations

import asyncio
import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from auditability.core.chain_verifier import verify_chain
from auditability.core.domain import AuditPackRecord, AuditPackStatus, new_id
from auditability.db.repository import SQLAlchemyAuditabilityRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["AUDITABILITY_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


@pytest.fixture(autouse=True)
async def _empty_audit_packs_table(migrated_url):
    """claim_next_audit_pack scans across all tenants by design -- so, unlike the
    tenant-scoped tests in this file, the audit-pack tests can't isolate themselves
    with a distinct tenant_id alone. Resets data (not schema) before each test."""
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("DELETE FROM audit_packs"))
            await conn.commit()
    finally:
        await engine.dispose()


async def test_concurrent_appends_for_the_same_tenant_never_collide_on_sequence_number(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async def append_one(i: int):
            async with engine.connect() as conn, AsyncSession(conn) as session:
                repo = SQLAlchemyAuditabilityRepository(session)
                return await repo.append_event(
                    tenant_id="concurrent-tenant", source_module=f"module-{i}", event_type="e", payload={"i": i},
                )

        results = await asyncio.gather(*(append_one(i) for i in range(8)))

        sequence_numbers = sorted(r.sequence_number for r in results)
        assert sequence_numbers == list(range(1, 9)), "no two concurrent writers may share a sequence_number"

        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyAuditabilityRepository(session)
            chain = await repo.list_events_for_chain("concurrent-tenant")
            result = verify_chain(chain)
            assert result.valid is True, "a correctly serialized chain must still verify end to end"
            assert result.verified_count == 8
    finally:
        await engine.dispose()


async def test_concurrent_audit_pack_claims_never_double_claim_the_same_row(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        pack_ids: list[str] = []
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyAuditabilityRepository(session)
            for _ in range(8):
                pack = await repo.create_audit_pack(
                    AuditPackRecord(id=new_id(), tenant_id="acme", status=AuditPackStatus.GENERATING)
                )
                pack_ids.append(pack.id)

        async def claim_one(worker_id: str) -> str | None:
            async with engine.connect() as conn, AsyncSession(conn) as session:
                repo = SQLAlchemyAuditabilityRepository(session)
                claimed = await repo.claim_next_audit_pack(worker_id, lease_seconds=120)
                return claimed.id if claimed else None

        results = await asyncio.gather(*(claim_one(f"worker-{i}") for i in range(4)))

        assert all(r is not None for r in results)
        assert len(set(results)) == 4
        assert set(results) <= set(pack_ids)
    finally:
        await engine.dispose()
