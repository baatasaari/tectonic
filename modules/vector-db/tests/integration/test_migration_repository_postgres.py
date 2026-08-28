"""Integration tier: SQLAlchemyMigrationRepository against a real Postgres
-- proves the independent architecture assessment's §10 Vector DB fix
("migration state is in memory") actually persists, and that its
session-per-call design (see db/repository.py's own docstring) is safe
under concurrent callers, the exact shape it's used in production:
called both from a request handler and from a detached
asyncio.create_task. See conftest.py for how the Postgres instance is
obtained.
"""
from __future__ import annotations

import asyncio
import os

import pytest
from alembic.config import Config as AlembicConfig

from alembic import command
from vector_db.core.domain import MigrationRecord, MigrationStatus, new_id
from vector_db.db.repository import SQLAlchemyMigrationRepository
from vector_db.db.session import make_engine, make_session_factory

pytestmark = pytest.mark.asyncio


class _Settings:
    def __init__(self, url: str) -> None:
        self.database_url = url
        self.db_pool_size = 5
        self.db_max_overflow = 2
        self.db_pool_timeout_seconds = 30
        self.db_pool_recycle_seconds = 1800


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["VECTOR_DB_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_create_get_update_round_trips(migrated_url):
    engine = make_engine(_Settings(migrated_url))
    try:
        repo = SQLAlchemyMigrationRepository(make_session_factory(engine))
        record = MigrationRecord(
            id=new_id(), tenant_id="acme", source_collection="src", target_collection="dst",
            target_embedding_model="text-embedding-3-large", points_total=100,
        )
        created = await repo.create(record)
        assert created.status == MigrationStatus.RUNNING

        fetched = await repo.get(created.id)
        assert fetched is not None
        assert fetched.points_total == 100
        assert fetched.points_migrated == 0

        fetched.points_migrated = 100
        fetched.status = MigrationStatus.COMPLETED
        from vector_db.core.domain import now

        fetched.completed_at = now()
        updated = await repo.update(fetched)

        assert updated.status == MigrationStatus.COMPLETED
        assert updated.points_migrated == 100
        assert updated.completed_at is not None

        refetched = await repo.get(created.id)
        assert refetched.status == MigrationStatus.COMPLETED
    finally:
        await engine.dispose()


async def test_get_returns_none_for_an_unknown_id(migrated_url):
    engine = make_engine(_Settings(migrated_url))
    try:
        repo = SQLAlchemyMigrationRepository(make_session_factory(engine))
        # A real, well-formed UUID that was simply never created -- the id column is a
        # native Postgres uuid type, so an arbitrary non-UUID string (fine against the
        # in-memory fake's plain dict lookup) raises a DB-level error here instead of
        # cleanly returning None; a valid-but-unknown UUID is the real "not found" case.
        assert await repo.get(new_id()) is None
    finally:
        await engine.dispose()


async def test_the_repository_is_safe_to_share_across_concurrent_callers(migrated_url):
    """The exact shape this repository is actually used in: one long-
    lived instance (held on AppContext), called from many concurrent
    tasks -- a request handler and a detached asyncio.create_task alike.
    A single shared AsyncSession would not survive this; a fresh session
    per call (this repository's own design) does."""
    engine = make_engine(_Settings(migrated_url))
    try:
        repo = SQLAlchemyMigrationRepository(make_session_factory(engine))

        async def create_one(i: int) -> str:
            record = MigrationRecord(
                id=new_id(), tenant_id=f"tenant-{i}", source_collection="src", target_collection="dst",
                target_embedding_model="text-embedding-3-large",
            )
            created = await repo.create(record)
            return created.id

        ids = await asyncio.gather(*(create_one(i) for i in range(10)))

        assert len(set(ids)) == 10
        for migration_id in ids:
            assert await repo.get(migration_id) is not None
    finally:
        await engine.dispose()
