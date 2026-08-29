"""SQLAlchemy-backed implementation of MigrationRepository.

Unlike this platform's usual per-request-session repositories, this one
holds an `async_sessionmaker`, not a single `AsyncSession` -- it is
built once in `main.py`'s `build_app_context` and lives for the whole
process as part of `AppContext.migration_manager`, called both from
request handlers *and* from the detached `asyncio.create_task` a
migration run starts (`api/routes_vectors.py`), so it must be safe to
call concurrently from unrelated tasks. A single shared `AsyncSession`
is not safe for that (SQLAlchemy sessions are not concurrency-safe);
opening and closing a fresh session inside each method call is. This is
the same "safe to hold as a long-lived singleton, calls a fresh session
per operation" shape `OutboxRelayWorker`/`EvidencePackWorker` already
use via their own `repository_factory` callables elsewhere in this
platform, adapted here to a plain three-method repository instead of a
poll-loop worker.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vector_db.core.domain import MigrationRecord, MigrationStatus
from vector_db.db import models


def _is_valid_uuid(value: str) -> bool:
    """`id` is a Postgres `UUID`; a path-param `str` that isn't a
    syntactically valid UUID by definition names no row, but handing it
    to `asyncpg` regardless raises an unhandled `ValueError`/`DataError`
    deep in the driver instead of the caller's own `None`/404 path
    (found by this module's own OpenAPI contract-test tier -- see
    Billing and Metering's `db/repository.py` for the original instance
    of this exact fix)."""
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _to_domain(m: models.Migration) -> MigrationRecord:
    return MigrationRecord(
        id=str(m.id), tenant_id=m.tenant_id, source_collection=m.source_collection,
        target_collection=m.target_collection, target_embedding_model=m.target_embedding_model,
        status=MigrationStatus(m.status), points_total=m.points_total, points_migrated=m.points_migrated,
        created_at=m.created_at, completed_at=m.completed_at,
    )


class SQLAlchemyMigrationRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(self, record: MigrationRecord) -> MigrationRecord:
        async with self._session_factory() as session:
            m = models.Migration(
                id=record.id, tenant_id=record.tenant_id, source_collection=record.source_collection,
                target_collection=record.target_collection, target_embedding_model=record.target_embedding_model,
                status=record.status.value, points_total=record.points_total,
                points_migrated=record.points_migrated,
            )
            session.add(m)
            await session.commit()
            await session.refresh(m)
            return _to_domain(m)

    async def get(self, migration_id: str) -> MigrationRecord | None:
        if not _is_valid_uuid(migration_id):
            return None
        async with self._session_factory() as session:
            m = await session.get(models.Migration, migration_id)
            return _to_domain(m) if m else None

    async def update(self, record: MigrationRecord) -> MigrationRecord:
        async with self._session_factory() as session:
            m = await session.get(models.Migration, record.id)
            if m is None:
                raise LookupError(record.id)
            m.status = record.status.value
            m.points_total = record.points_total
            m.points_migrated = record.points_migrated
            m.completed_at = record.completed_at
            await session.commit()
            await session.refresh(m)
            return _to_domain(m)
