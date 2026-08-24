"""Integration tier (LLD §4 testing plan): the SQLAlchemy repository
against a real Postgres — not part of the default unit-test run. See
`conftest.py` for how the Postgres instance is obtained.

Specifically exercises what SQLite's unit-tier tests can't: real JSONB
list round-tripping (`DeletionRecord.memory_items_deleted`), a real UUID
primary key round trip through create + update, and a multi-row filtered
query (`list_active` scoped by memory type) that must hit only the
intended rows against genuine Postgres semantics.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from long_term_memory.core.domain import (
    DeletionRecord,
    MemoryItemRecord,
    MemoryItemStatus,
    MemoryType,
    new_id,
)
from long_term_memory.db.repository import SQLAlchemyLongTermMemoryRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["LONG_TERM_MEMORY_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_deletion_record_memory_items_deleted_round_trips_as_real_jsonb(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyLongTermMemoryRepository(session)
            item_ids = [new_id(), new_id(), new_id()]
            created = await repo.create_deletion_record(
                DeletionRecord(
                    id=new_id(), tenant_id="acme", subject_ref="user-42", memory_items_deleted=item_ids,
                    deletion_proof_hash="abc123", requested_by="dpo@acme.example",
                )
            )
            assert created.memory_items_deleted == item_ids

            # A real JSONB round trip preserves list order and element types exactly —
            # this is exactly the kind of thing SQLite's JSON-as-TEXT variant can
            # silently get away with getting wrong that Postgres's native JSONB won't.
            fetched = await repo.get_deletion_record("acme", created.id)
            assert fetched is not None
            assert fetched.memory_items_deleted == item_ids
    finally:
        await engine.dispose()


async def test_list_active_filters_by_memory_type_across_multiple_rows(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyLongTermMemoryRepository(session)
            fact = await repo.create_item(
                MemoryItemRecord(id=new_id(), tenant_id="acme", scope="user-1", memory_type=MemoryType.FACT, content="f1")
            )
            episodic = await repo.create_item(
                MemoryItemRecord(
                    id=new_id(), tenant_id="acme", scope="user-1", memory_type=MemoryType.EPISODIC, content="e1"
                )
            )
            semantic = await repo.create_item(
                MemoryItemRecord(
                    id=new_id(), tenant_id="acme", scope="user-1", memory_type=MemoryType.SEMANTIC, content="s1"
                )
            )
            decayed_fact = await repo.create_item(
                MemoryItemRecord(id=new_id(), tenant_id="acme", scope="user-1", memory_type=MemoryType.FACT, content="f2")
            )
            decayed_fact.status = MemoryItemStatus.DECAYED
            await repo.update_item(decayed_fact)

            # multi-row query hitting only the intended rows: correct tenant, ACTIVE
            # status only, and filtered to the requested memory_type subset.
            results = await repo.list_active("acme", memory_types=[MemoryType.FACT, MemoryType.SEMANTIC])
            result_ids = {r.id for r in results}
            assert result_ids == {fact.id, semantic.id}
            assert episodic.id not in result_ids
            assert decayed_fact.id not in result_ids
    finally:
        await engine.dispose()


async def test_memory_item_real_uuid_pk_round_trips_through_update(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyLongTermMemoryRepository(session)
            item = await repo.create_item(
                MemoryItemRecord(
                    id=new_id(), tenant_id="acme", scope="user-1", memory_type=MemoryType.PROCEDURAL,
                    content="how to file an expense report",
                )
            )
            # a real UUID (asyncpg returns/accepts a genuine UUID type; SQLite's
            # CHAR(36) variant just stores it as a plain string) — confirm it round-trips
            # as a fetchable primary key across an update, not just a string that happens
            # to look like one.
            item.status = MemoryItemStatus.CONSOLIDATED
            item.relevance_score = 0.42
            item.vector_ref = "vec-99"
            updated = await repo.update_item(item)
            assert updated.id == item.id

            fetched = await repo.get_item("acme", item.id)
            assert fetched is not None
            assert fetched.id == item.id
            assert fetched.status == MemoryItemStatus.CONSOLIDATED
            assert fetched.relevance_score == 0.42
            assert fetched.vector_ref == "vec-99"
    finally:
        await engine.dispose()
