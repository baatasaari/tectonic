"""Integration tier (LLD §4 testing plan): the SQLAlchemy repository
against a real Postgres — not part of the default unit-test run. See
`conftest.py` for how the Postgres instance is obtained.

Specifically exercises what SQLite's unit-tier tests can't: `ToolDefinition`'s
nested JSON-Schema-shaped `schema` dict round-tripping through real JSONB
alongside a real UUID primary key, a multi-row `list_tool_definitions` query
filtered by tenant *and* status that must hit only the intended rows, and an
upsert-style `upsert_reliability_score` that must update only the targeted
tool's row, leaving a sibling tool's row untouched.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from tool_orchestration.core.domain import (
    ReliabilityScoreRecord,
    ToolDefinitionRecord,
    ToolStatus,
    new_id,
)
from tool_orchestration.db.repository import SQLAlchemyToolRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["TOOL_ORCHESTRATION_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_tool_definition_schema_round_trips_as_real_jsonb_with_real_uuid_pk(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyToolRepository(session)
            schema = {
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["query"],
            }
            created = await repo.create_tool_definition(
                ToolDefinitionRecord(
                    id=new_id(), tenant_id="acme", name="search_docs", mcp_server_ref="mcp-1", schema=schema,
                )
            )
            # A real JSONB round trip preserves nested dict structure, key order, and
            # element types exactly — this is exactly the kind of thing SQLite's
            # JSON-as-TEXT variant can silently get away with getting wrong.
            assert created.schema == schema

            # asyncpg returns/accepts a genuine UUID type for the primary key; SQLite's
            # CHAR(36) variant just stores it as a plain string. Confirm it round-trips
            # as a fetchable primary key against real Postgres UUID semantics.
            fetched = await repo.get_tool_definition(created.id)
            assert fetched is not None
            assert fetched.id == created.id
            assert fetched.schema == schema
            assert fetched.schema["properties"]["limit"]["type"] == "integer"
    finally:
        await engine.dispose()


async def test_list_tool_definitions_filters_by_tenant_and_status(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyToolRepository(session)
            await repo.create_tool_definition(
                ToolDefinitionRecord(
                    id=new_id(), tenant_id="beta-corp", name="tool_a", mcp_server_ref="mcp-1",
                    status=ToolStatus.ACTIVE,
                )
            )
            await repo.create_tool_definition(
                ToolDefinitionRecord(
                    id=new_id(), tenant_id="beta-corp", name="tool_b", mcp_server_ref="mcp-1",
                    status=ToolStatus.DEPRECATED,
                )
            )
            await repo.create_tool_definition(
                ToolDefinitionRecord(
                    id=new_id(), tenant_id="other-corp", name="tool_c", mcp_server_ref="mcp-1",
                    status=ToolStatus.ACTIVE,
                )
            )

            active_for_beta, _total = await repo.list_tool_definitions("beta-corp", status="active")

            # A multi-row filtered query against real Postgres must hit exactly the
            # rows matching both predicates, no more and no less.
            assert len(active_for_beta) == 1
            assert active_for_beta[0].name == "tool_a"
    finally:
        await engine.dispose()


async def test_upsert_reliability_score_updates_only_the_targeted_tool(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyToolRepository(session)
            tool_a = await repo.create_tool_definition(
                ToolDefinitionRecord(id=new_id(), tenant_id="acme", name="tool_a", mcp_server_ref="mcp-1")
            )
            tool_b = await repo.create_tool_definition(
                ToolDefinitionRecord(id=new_id(), tenant_id="acme", name="tool_b", mcp_server_ref="mcp-1")
            )
            await repo.upsert_reliability_score(
                ReliabilityScoreRecord(tool_id=tool_a.id, rolling_success_rate=0.9, rolling_avg_latency_ms=120.0)
            )
            await repo.upsert_reliability_score(
                ReliabilityScoreRecord(tool_id=tool_b.id, rolling_success_rate=0.5, rolling_avg_latency_ms=800.0)
            )

            # Re-upsert (update path) tool_a's score only.
            await repo.upsert_reliability_score(
                ReliabilityScoreRecord(tool_id=tool_a.id, rolling_success_rate=0.99, rolling_avg_latency_ms=95.0)
            )

            score_a = await repo.get_reliability_score(tool_a.id)
            score_b = await repo.get_reliability_score(tool_b.id)
            assert score_a is not None and score_a.rolling_success_rate == 0.99
            # The sibling tool's row must remain untouched by the targeted update.
            assert score_b is not None and score_b.rolling_success_rate == 0.5
            assert score_b.rolling_avg_latency_ms == 800.0
    finally:
        await engine.dispose()
