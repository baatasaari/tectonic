"""Integration tier: proves things SQLite's unit-tier fakes can't
reliably prove -- real Postgres round-tripping for developer status
transitions, the catalogue's JSON `spec_json` column and its upsert
(same primary key, new content), and SDK package version ordering.
See `conftest.py` for how the Postgres instance is obtained.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from sdk_and_developer_portal.core.domain import (
    DeveloperAccountRecord,
    DeveloperStatus,
    ModuleCatalogEntryRecord,
    SdkPackageRecord,
    new_id,
)
from sdk_and_developer_portal.db.repository import SQLAlchemyPortalRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["SDKPORTAL_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_developer_status_transition_round_trips(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyPortalRepository(session)
            developer = await repo.create_developer(DeveloperAccountRecord(
                id=new_id(), name="Ada", email="ada@example.com", tenant_id="t1", identity_id="i1",
            ))

            developer.status = DeveloperStatus.REVOKED
            updated = await repo.update_developer(developer)

            fetched = await repo.get_developer(developer.id)
            assert fetched.status == DeveloperStatus.REVOKED
            assert updated.status == DeveloperStatus.REVOKED
    finally:
        await engine.dispose()


async def test_catalog_entry_upsert_replaces_content_for_the_same_module(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyPortalRepository(session)
            module_name = f"mod-{new_id()[:8]}"
            await repo.upsert_catalog_entry(ModuleCatalogEntryRecord(
                module_name=module_name, base_url="http://x", title="X", version="1.0.0",
                path_count=1, spec_json={"paths": {"/a": {}}}, spec_hash="hash-v1",
            ))
            await repo.upsert_catalog_entry(ModuleCatalogEntryRecord(
                module_name=module_name, base_url="http://x", title="X", version="1.1.0",
                path_count=2, spec_json={"paths": {"/a": {}, "/b": {}}}, spec_hash="hash-v2",
            ))

            fetched = await repo.get_catalog_entry(module_name)
            assert fetched.version == "1.1.0"
            assert fetched.spec_hash == "hash-v2"
            assert fetched.spec_json == {"paths": {"/a": {}, "/b": {}}}
    finally:
        await engine.dispose()


async def test_get_latest_sdk_package_returns_the_highest_version(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyPortalRepository(session)
            module_name = f"mod-{new_id()[:8]}"
            await repo.create_sdk_package(SdkPackageRecord(
                id=new_id(), module_name=module_name, language="python", version=1,
                source_code="# v1", spec_hash="h1",
            ))
            await repo.create_sdk_package(SdkPackageRecord(
                id=new_id(), module_name=module_name, language="python", version=2,
                source_code="# v2", spec_hash="h2",
            ))

            latest = await repo.get_latest_sdk_package(module_name=module_name, language="python")
            assert latest.version == 2
            assert latest.spec_hash == "h2"
    finally:
        await engine.dispose()


async def test_list_developers_filters_by_status(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyPortalRepository(session)
            active = await repo.create_developer(DeveloperAccountRecord(
                id=new_id(), name="Active", email="a@example.com", tenant_id="t1", identity_id="i1",
            ))
            revoked = await repo.create_developer(DeveloperAccountRecord(
                id=new_id(), name="Revoked", email="r@example.com", tenant_id="t2", identity_id="i2",
            ))
            revoked.status = DeveloperStatus.REVOKED
            await repo.update_developer(revoked)

            active_results, _total = await repo.list_developers(status=DeveloperStatus.ACTIVE, limit=200)
            active_ids = {d.id for d in active_results}

            assert active.id in active_ids
            assert revoked.id not in active_ids
    finally:
        await engine.dispose()
