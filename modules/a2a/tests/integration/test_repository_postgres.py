"""Integration tier: proves things SQLite's unit-tier fakes can't reliably
prove -- real JSONB round-tripping for task input/output payloads and
nullable access-policy allow-lists, the agent-card cache's upsert
semantics, and `list_tasks`' pagination/direction filter against real
Postgres. See `conftest.py` for how the Postgres instance is obtained.
"""
from __future__ import annotations

import os
from datetime import timedelta

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from a2a_gateway.core.domain import (
    A2AAccessPolicyRecord,
    A2ATaskRecord,
    AgentCardCacheEntry,
    TaskDirection,
    TaskStatus,
    new_id,
    now,
)
from a2a_gateway.db.repository import SQLAlchemyA2AGatewayRepository
from alembic import command

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["A2A_GATEWAY_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_task_input_and_output_round_trip_as_real_jsonb_with_nested_structure(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyA2AGatewayRepository(session)
            input_message = {"text": "hello", "nested": {"a": [1, 2, 3]}}
            task = await repo.create_task(
                A2ATaskRecord(
                    id=new_id(), tenant_id="acme", direction=TaskDirection.OUTBOUND, peer_agent_url="http://peer",
                    skill_id="summarize", input_message=input_message,
                )
            )
            artifacts = [{"summary": "done", "detail": {"nested": ["x", "y"]}}]
            updated = await repo.update_task_status(task.id, status=TaskStatus.COMPLETED, output_artifacts=artifacts)

            fetched = await repo.get_task(task.id)

            # Real JSONB round trip preserves nested dict/list structure and types exactly
            # -- SQLite's JSON-as-TEXT variant can silently get this wrong.
            assert fetched.input_message == input_message
            assert fetched.output_artifacts == artifacts
            assert fetched.status == TaskStatus.COMPLETED
            assert updated.status == TaskStatus.COMPLETED
    finally:
        await engine.dispose()


async def test_access_policy_allowed_skills_null_means_full_access_then_upsert_updates_in_place(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyA2AGatewayRepository(session)

            await repo.upsert_access_policy(
                A2AAccessPolicyRecord(id=new_id(), caller_agent_id="peer-1", tenant_id="acme", allowed_skills=None)
            )
            fetched = await repo.get_access_policy("peer-1", "acme")
            assert fetched.allowed_skills is None

            # Upsert again with a concrete allow-list -- must update the existing row, not
            # insert a second one (the UniqueConstraint on (caller_agent_id, tenant_id) would reject a dupe).
            await repo.upsert_access_policy(
                A2AAccessPolicyRecord(id=new_id(), caller_agent_id="peer-1", tenant_id="acme", allowed_skills=["summarize"])
            )
            refetched = await repo.get_access_policy("peer-1", "acme")

            assert refetched.allowed_skills == ["summarize"]
    finally:
        await engine.dispose()


async def test_agent_card_cache_upsert_replaces_the_existing_entry_for_the_same_url(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyA2AGatewayRepository(session)
            entry = AgentCardCacheEntry(
                id=new_id(), agent_url="http://peer", card={"name": "peer-v1"},
                fetched_at=now(), expires_at=now() + timedelta(hours=1),
            )
            await repo.upsert_cached_card(entry)

            refreshed = AgentCardCacheEntry(
                id=new_id(), agent_url="http://peer", card={"name": "peer-v2"},
                fetched_at=now(), expires_at=now() + timedelta(hours=1),
            )
            await repo.upsert_cached_card(refreshed)

            cached = await repo.get_cached_card("http://peer")
            assert cached.card == {"name": "peer-v2"}
    finally:
        await engine.dispose()


async def test_list_tasks_pagination_and_direction_filter(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyA2AGatewayRepository(session)
            for i in range(3):
                await repo.create_task(
                    A2ATaskRecord(
                        id=new_id(), tenant_id="page-tenant", direction=TaskDirection.OUTBOUND,
                        peer_agent_url=f"http://{i}", skill_id="summarize",
                    )
                )
            await repo.create_task(
                A2ATaskRecord(
                    id=new_id(), tenant_id="page-tenant", direction=TaskDirection.INBOUND,
                    peer_agent_url="http://inbound-peer", skill_id="summarize",
                )
            )

            outbound, total_outbound = await repo.list_tasks(
                tenant_id="page-tenant", direction=TaskDirection.OUTBOUND, limit=2, offset=0,
            )
            page2, _ = await repo.list_tasks(tenant_id="page-tenant", direction=TaskDirection.OUTBOUND, limit=2, offset=2)

            assert total_outbound == 3
            assert len(outbound) == 2
            assert len(page2) == 1
            assert {t.id for t in outbound}.isdisjoint({t.id for t in page2})
    finally:
        await engine.dispose()
