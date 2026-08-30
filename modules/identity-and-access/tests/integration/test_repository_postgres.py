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
    PLATFORM_TENANT_ID,
    AuthDecisionRecord,
    IdentityRecord,
    IdentityStatus,
    IdentityType,
    RoleBindingRecord,
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

            fetched = await repo.get_role(created.tenant_id, created.name)
            assert fetched.scopes == ["cards:read", "cards:list"]
    finally:
        await engine.dispose()


async def test_two_tenants_can_own_a_role_with_the_same_name(migrated_url):
    """Real-Postgres proof of the IAM v2 tenant-scoped-roles fix: the
    unique constraint is on (tenant_id, name), not on name alone."""
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyIdentityAccessRepository(session)
            role_name = f"admin-{new_id()[:8]}"
            acme_role = await repo.create_role(
                RoleRecord(tenant_id="acme-pg", name=role_name, scopes=["cards:admin"])
            )
            globex_role = await repo.create_role(
                RoleRecord(tenant_id="globex-pg", name=role_name, scopes=["cards:read"])
            )

            assert acme_role.id != globex_role.id
            assert (await repo.get_role("acme-pg", role_name)).scopes == ["cards:admin"]
            assert (await repo.get_role("globex-pg", role_name)).scopes == ["cards:read"]
    finally:
        await engine.dispose()


async def test_get_role_falls_back_to_the_platform_wide_default(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyIdentityAccessRepository(session)
            role_name = f"viewer-{new_id()[:8]}"
            await repo.create_role(RoleRecord(tenant_id=PLATFORM_TENANT_ID, name=role_name, scopes=["cards:read"]))

            fetched = await repo.get_role("some-tenant-with-no-custom-role", role_name)
            assert fetched is not None
            assert fetched.tenant_id == PLATFORM_TENANT_ID
    finally:
        await engine.dispose()


async def test_role_binding_grant_and_revoke_round_trip(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyIdentityAccessRepository(session)
            identity_id = new_id()
            binding = await repo.create_role_binding(
                RoleBindingRecord(
                    id=new_id(), tenant_id="acme-pg", identity_id=identity_id,
                    role_name="reader", granted_by="operator-1",
                )
            )
            assert binding.revoked_at is None

            active = await repo.get_active_role_binding(identity_id=identity_id, role_name="reader")
            assert active is not None
            assert active.id == binding.id

            revoked = await repo.revoke_role_binding(binding.id)
            assert revoked.revoked_at is not None

            assert await repo.get_active_role_binding(identity_id=identity_id, role_name="reader") is None

            bindings, total = await repo.list_role_bindings(identity_id=identity_id)
            assert total == 1
            assert bindings[0].granted_by == "operator-1"
            assert bindings[0].revoked_at is not None
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


async def test_a_non_uuid_lookup_id_returns_none_instead_of_crashing(migrated_url):
    """The "non-UUID path/query-param" bug class this platform has already
    hit repeatedly (ticket #82's own sweep) recurred here too: `id` columns
    are Postgres `UUID`, so handing a syntactically-invalid one straight to
    `session.get()` raises an unhandled `asyncpg.exceptions.DataError`
    instead of the caller's own clean `None`/404 path -- SQLite's unit-tier
    fake can't reproduce this (a dict lookup never crashes on a malformed
    key), so this is real-Postgres-only coverage, found by this module's
    own OpenAPI contract-test tier's very first run against `GET
    /identities/{identity_id}`. Covers every lookup-by-externally-supplied-
    id repository method this fix touched."""
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyIdentityAccessRepository(session)

            assert await repo.get_identity("not-a-uuid") is None
            assert await repo.get_identity_provider("not-a-uuid") is None
            assert await repo.get_group("not-a-uuid") is None
            assert await repo.revoke_scim_token("not-a-uuid") is None
    finally:
        await engine.dispose()
