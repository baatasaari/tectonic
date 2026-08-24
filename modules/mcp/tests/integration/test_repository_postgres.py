"""Integration tier: proves things SQLite's unit-tier fakes can't reliably
prove -- real JSONB round-tripping for tool input schemas and nullable
access-policy allow-lists, and `list_servers`' pagination against real
Postgres. See `conftest.py` for how the Postgres instance is obtained.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from mcp_gateway.core.domain import AccessPolicyRecord, McpServerRecord, McpToolRecord, new_id
from mcp_gateway.db.repository import SQLAlchemyMCPGatewayRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["MCP_GATEWAY_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_tool_input_schema_round_trips_as_real_jsonb_with_nested_structure(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMCPGatewayRepository(session)
            server = await repo.create_server(
                McpServerRecord(id=new_id(), tenant_id="acme", name="s", description="", base_url="http://b")
            )
            schema = {"type": "object", "properties": {"q": {"type": "string"}}, "nested": {"a": [1, 2, 3]}}
            await repo.replace_tools(
                server.id,
                [McpToolRecord(id=new_id(), server_id=server.id, name="search", description="", input_schema=schema)],
            )

            tools = await repo.list_tools(server.id)

            assert len(tools) == 1
            # Real JSONB round trip preserves nested dict/list structure and types exactly
            # -- SQLite's JSON-as-TEXT variant can silently get this wrong.
            assert tools[0].input_schema == schema
    finally:
        await engine.dispose()


async def test_access_policy_allowed_tools_null_means_full_access_round_trip(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMCPGatewayRepository(session)
            server = await repo.create_server(
                McpServerRecord(id=new_id(), tenant_id="acme", name="s", description="", base_url="http://b")
            )

            upserted = await repo.upsert_access_policy(
                AccessPolicyRecord(id=new_id(), server_id=server.id, tenant_id="acme", allowed_tools=None)
            )
            fetched = await repo.get_access_policy(server.id, "acme")

            assert upserted.allowed_tools is None
            assert fetched.allowed_tools is None

            # Upsert again with a concrete allow-list -- must update the existing row, not
            # insert a second one (the UniqueConstraint on (server_id, tenant_id) would reject a dupe).
            await repo.upsert_access_policy(
                AccessPolicyRecord(id=new_id(), server_id=server.id, tenant_id="acme", allowed_tools=["search"])
            )
            refetched = await repo.get_access_policy(server.id, "acme")

            assert refetched.allowed_tools == ["search"]
    finally:
        await engine.dispose()


async def test_list_servers_pagination_hits_only_the_intended_rows(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMCPGatewayRepository(session)
            for i in range(5):
                await repo.create_server(
                    McpServerRecord(
                        id=new_id(), tenant_id="page-tenant", name=f"s{i}", description="", base_url=f"http://{i}",
                    )
                )

            page1, total1 = await repo.list_servers(tenant_id="page-tenant", limit=2, offset=0)
            page2, total2 = await repo.list_servers(tenant_id="page-tenant", limit=2, offset=2)

            assert total1 == total2 == 5
            assert len(page1) == 2
            assert len(page2) == 2
            assert {s.id for s in page1}.isdisjoint({s.id for s in page2})
    finally:
        await engine.dispose()


async def test_list_servers_filters_by_tenant_id(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyMCPGatewayRepository(session)
            await repo.create_server(
                McpServerRecord(id=new_id(), tenant_id="tenant-a", name="a", description="", base_url="http://a")
            )
            await repo.create_server(
                McpServerRecord(id=new_id(), tenant_id="tenant-b", name="b", description="", base_url="http://b")
            )

            servers, total = await repo.list_servers(tenant_id="tenant-a")

            assert total == 1
            assert servers[0].tenant_id == "tenant-a"
    finally:
        await engine.dispose()
