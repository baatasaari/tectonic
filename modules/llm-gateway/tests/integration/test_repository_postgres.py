"""Integration tier (LLD §4 testing plan): the SQLAlchemy repository
against a real Postgres — not part of the default unit-test run. See
`conftest.py` for how the Postgres instance is obtained.

Specifically exercises what SQLite's unit-tier tests can't: `VirtualKey`'s
`provider_scope` list round-tripping through real JSONB alongside a real
UUID primary key, `ProviderConfig.deprecation_notices` (a list of dicts)
round-tripping with exact structure/order preservation, and a multi-row
`list_virtual_keys` query that must hit only the intended tenant's rows.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from llm_gateway.core.domain import ProviderConfigRecord, VirtualKeyRecord, new_id
from llm_gateway.db.repository import SQLAlchemyGatewayRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["LLM_GATEWAY_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_virtual_key_provider_scope_round_trips_as_real_jsonb_with_real_uuid_pk(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyGatewayRepository(session)
            created = await repo.create_virtual_key(
                VirtualKeyRecord(
                    id=new_id(), tenant_id="acme", provider_scope=["anthropic", "openai", "azure"],
                    budget_policy_ref="bp-1",
                )
            )
            # A real JSONB round trip preserves list order and element types — this is
            # exactly the kind of thing SQLite's JSON-as-TEXT variant can silently get
            # away with getting wrong that Postgres's native JSONB type won't.
            assert created.provider_scope == ["anthropic", "openai", "azure"]

            # asyncpg returns/accepts a genuine UUID type for the primary key; SQLite's
            # CHAR(36) variant just stores it as a plain string. Confirm it round-trips
            # as a fetchable primary key against real Postgres UUID semantics.
            fetched = await repo.get_virtual_key(created.id)
            assert fetched is not None
            assert fetched.id == created.id
            assert fetched.provider_scope == ["anthropic", "openai", "azure"]
    finally:
        await engine.dispose()


async def test_create_provider_config_round_trips_and_rejects_duplicate_name(migrated_url):
    """`create_provider_config` (ticket #82) is the first real way, through
    this module's own repository, to provision a provider at all -- before
    this, a provider row could only be inserted directly against the
    SQLAlchemy model (see the previous version of this file), which is not
    something a real running deployment could ever do through this module's
    own API surface."""
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyGatewayRepository(session)
            created = await repo.create_provider_config(
                ProviderConfigRecord(id=new_id(), provider_name="acme-mock-llm", endpoint="http://localhost:9200", priority=1)
            )
            assert created.provider_name == "acme-mock-llm"
            assert created.health_status == "healthy"

            fetched = [p for p in await repo.list_provider_configs() if p.id == created.id]
            assert len(fetched) == 1
            assert fetched[0].endpoint == "http://localhost:9200"

            with pytest.raises(IntegrityError):
                await repo.create_provider_config(
                    ProviderConfigRecord(id=new_id(), provider_name="acme-mock-llm", endpoint="http://other", priority=2)
                )
    finally:
        await engine.dispose()


async def test_provider_config_deprecation_notices_round_trip_list_of_dicts(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyGatewayRepository(session)
            provider_id = new_id()
            await repo.create_provider_config(
                ProviderConfigRecord(id=provider_id, provider_name="openai", endpoint="https://api.openai.com/v1", priority=1)
            )

            notices = [
                {"model": "gpt-4-32k", "sunset_date": "2026-06-01", "replacement": "gpt-4.1"},
                {"model": "text-davinci-003", "sunset_date": "2024-01-04", "replacement": "gpt-3.5-turbo"},
            ]
            updated = await repo.update_provider_config(
                ProviderConfigRecord(
                    id=provider_id, provider_name="openai", endpoint="https://api.openai.com/v1",
                    priority=2, health_status="degraded", deprecation_notices=notices,
                )
            )
            assert updated.deprecation_notices == notices

            fetched = [p for p in await repo.list_provider_configs() if p.id == provider_id]
            assert len(fetched) == 1
            # Order and nested key/value types survive a real JSONB round trip.
            assert fetched[0].deprecation_notices == notices
            assert fetched[0].deprecation_notices[0]["model"] == "gpt-4-32k"
    finally:
        await engine.dispose()


async def test_list_virtual_keys_returns_only_matching_tenant_rows(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyGatewayRepository(session)
            await repo.create_virtual_key(
                VirtualKeyRecord(id=new_id(), tenant_id="initech", provider_scope=[], budget_policy_ref="bp-a")
            )
            await repo.create_virtual_key(
                VirtualKeyRecord(id=new_id(), tenant_id="initech", provider_scope=[], budget_policy_ref="bp-a2")
            )
            await repo.create_virtual_key(
                VirtualKeyRecord(id=new_id(), tenant_id="globex", provider_scope=[], budget_policy_ref="bp-b")
            )

            initech_keys, _total = await repo.list_virtual_keys("initech")

            # A multi-row filtered query against real Postgres must hit exactly the
            # intended tenant's rows, no more and no less.
            assert len(initech_keys) == 2
            assert {k.tenant_id for k in initech_keys} == {"initech"}
    finally:
        await engine.dispose()
