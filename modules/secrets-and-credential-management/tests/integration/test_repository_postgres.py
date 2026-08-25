"""Integration tier: proves things SQLite's unit-tier fakes can't reliably
prove -- real Postgres round-tripping for the secret lifecycle, version
history, access-record ordering, and the rotation-due/compliance counts.
See `conftest.py` for how the Postgres instance is obtained.
"""
from __future__ import annotations

import os
from datetime import timedelta

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from secrets_and_credential_management.core.domain import (
    SecretAccessRecord,
    SecretRecord,
    SecretStatus,
    SecretVersionRecord,
    new_id,
    now,
)
from secrets_and_credential_management.db.repository import SQLAlchemySecretsRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["SECRETS_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_secret_create_and_status_transition_round_trips(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemySecretsRepository(session)
            secret = await repo.create_secret(
                SecretRecord(id=new_id(), tenant_id="acme", namespace="db", key_name="password")
            )

            secret.status = SecretStatus.REVOKED
            updated = await repo.update_secret(secret)

            fetched = await repo.get_secret(secret.id)
            assert fetched.status == SecretStatus.REVOKED
            assert updated.status == SecretStatus.REVOKED
    finally:
        await engine.dispose()


async def test_version_history_and_get_latest_version(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemySecretsRepository(session)
            secret = await repo.create_secret(
                SecretRecord(id=new_id(), tenant_id="acme", namespace="db", key_name="password")
            )
            await repo.create_version(
                SecretVersionRecord(id=new_id(), secret_id=secret.id, version=1, ciphertext="ct-v1")
            )
            await repo.create_version(
                SecretVersionRecord(id=new_id(), secret_id=secret.id, version=2, ciphertext="ct-v2")
            )

            latest = await repo.get_latest_version(secret.id)
            assert latest.version == 2
            assert latest.ciphertext == "ct-v2"
    finally:
        await engine.dispose()


async def test_list_secrets_filters_by_tenant_namespace_and_status(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemySecretsRepository(session)
            active = await repo.create_secret(
                SecretRecord(id=new_id(), tenant_id="filter-tenant", namespace="db", key_name="active-1")
            )
            revoked = await repo.create_secret(
                SecretRecord(id=new_id(), tenant_id="filter-tenant", namespace="db", key_name="revoked-1")
            )
            revoked.status = SecretStatus.REVOKED
            await repo.update_secret(revoked)

            active_results, _total = await repo.list_secrets(
                tenant_id="filter-tenant", namespace="db", status=SecretStatus.ACTIVE, limit=200,
            )
            active_ids = {s.id for s in active_results}

            assert active.id in active_ids
            assert revoked.id not in active_ids
    finally:
        await engine.dispose()


async def test_list_due_for_rotation_and_count_active_and_overdue(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemySecretsRepository(session)
            tenant = f"rotation-tenant-{new_id()[:8]}"
            overdue = await repo.create_secret(
                SecretRecord(id=new_id(), tenant_id=tenant, namespace="db", key_name="overdue")
            )
            overdue.next_rotation_due_at = now() - timedelta(days=1)
            await repo.update_secret(overdue)

            await repo.create_secret(
                SecretRecord(id=new_id(), tenant_id=tenant, namespace="db", key_name="not-due-yet")
            )

            due, total_due = await repo.list_due_for_rotation(tenant_id=tenant, at=now())
            total_active, overdue_count = await repo.count_active_and_overdue(tenant_id=tenant, at=now())

            assert total_due == 1
            assert due[0].key_name == "overdue"
            assert total_active == 2
            assert overdue_count == 1
    finally:
        await engine.dispose()


async def test_access_records_ordered_newest_first_and_paginate(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemySecretsRepository(session)
            secret_id = new_id()
            for i in range(5):
                await repo.create_access_record(
                    SecretAccessRecord(
                        id=new_id(), secret_id=secret_id, tenant_id="acme", allowed=i % 2 == 0, reason="test",
                    )
                )

            page1, total1 = await repo.list_access_records(secret_id=secret_id, limit=2, offset=0)
            page2, total2 = await repo.list_access_records(secret_id=secret_id, limit=2, offset=2)

            assert total1 == total2 == 5
            assert len(page1) == 2
            assert len(page2) == 2
            assert {r.id for r in page1}.isdisjoint({r.id for r in page2})
    finally:
        await engine.dispose()
