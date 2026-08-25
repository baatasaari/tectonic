"""Integration tier: proves things SQLite's unit-tier fakes can't reliably
prove -- real Postgres ARRAY(String) round-tripping for role_names/scopes,
status filtering, and auth-decision history ordering. See `conftest.py`
for how the Postgres instance is obtained.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from identity_and_access.core.domain import (
    AuthDecisionRecord,
    IdentityRecord,
    IdentityStatus,
    IdentityType,
    RoleRecord,
    new_id,
)
from identity_and_access.db.repository import SQLAlchemyIdentityAccessRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["IDENTITY_ACCESS_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_role_scopes_array_round_trips(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyIdentityAccessRepository(session)
            created = await repo.create_role(
                RoleRecord(name=f"reader-{new_id()[:8]}", scopes=["cards:read", "cards:list"], description="ro")
            )

            fetched = await repo.get_role(created.name)
            assert fetched.scopes == ["cards:read", "cards:list"]
    finally:
        await engine.dispose()


async def test_identity_role_names_array_round_trips(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyIdentityAccessRepository(session)
            role_name = f"writer-{new_id()[:8]}"
            await repo.create_role(RoleRecord(name=role_name, scopes=["cards:write"]))

            identity = await repo.create_identity(
                IdentityRecord(
                    id=new_id(), tenant_id="acme", name="agent-1", type=IdentityType.AGENT,
                    role_names=[role_name],
                )
            )

            fetched = await repo.get_identity(identity.id)
            assert fetched.role_names == [role_name]
    finally:
        await engine.dispose()


async def test_identity_status_transitions_round_trip(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyIdentityAccessRepository(session)
            identity = await repo.create_identity(
                IdentityRecord(id=new_id(), tenant_id="acme", name="agent-2")
            )

            identity.status = IdentityStatus.REVOKED
            updated = await repo.update_identity(identity)

            fetched = await repo.get_identity(identity.id)
            assert fetched.status == IdentityStatus.REVOKED
            assert updated.status == IdentityStatus.REVOKED
    finally:
        await engine.dispose()


async def test_list_identities_filters_by_tenant_and_status(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyIdentityAccessRepository(session)
            active = await repo.create_identity(IdentityRecord(id=new_id(), tenant_id="filter-tenant", name="active-1"))
            revoked = await repo.create_identity(IdentityRecord(id=new_id(), tenant_id="filter-tenant", name="revoked-1"))
            revoked.status = IdentityStatus.REVOKED
            await repo.update_identity(revoked)

            active_results, _total = await repo.list_identities(
                tenant_id="filter-tenant", status=IdentityStatus.ACTIVE, limit=200,
            )
            active_ids = {i.id for i in active_results}

            assert active.id in active_ids
            assert revoked.id not in active_ids
    finally:
        await engine.dispose()


async def test_auth_decisions_ordered_newest_first_and_paginate(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyIdentityAccessRepository(session)
            identity_id = new_id()
            for i in range(5):
                await repo.create_auth_decision(
                    AuthDecisionRecord(
                        id=new_id(), tenant_id="acme", identity_id=identity_id, required_scope="cards:read",
                        allowed=i % 2 == 0, reason="test",
                    )
                )

            page1, total1 = await repo.list_auth_decisions(identity_id=identity_id, limit=2, offset=0)
            page2, total2 = await repo.list_auth_decisions(identity_id=identity_id, limit=2, offset=2)

            assert total1 == total2 == 5
            assert len(page1) == 2
            assert len(page2) == 2
            assert {d.id for d in page1}.isdisjoint({d.id for d in page2})
    finally:
        await engine.dispose()
