"""Integration tier (LLD §4.8): the SQLAlchemy repository against a real
Postgres — not part of the default unit-test run. See `conftest.py` for how
the Postgres instance is obtained (either `TECTONIC_TEST_POSTGRES_URL`
against an already-running Postgres, or testcontainers/Docker as fallback).
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from workflow_engine.core.domain import (
    DefinitionStatus,
    WorkflowDefinitionRecord,
    WorkflowInstanceRecord,
    new_id,
)
from workflow_engine.db.repository import SQLAlchemyWorkflowRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["WORKFLOW_ENGINE_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_create_and_fetch_definition_round_trips(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyWorkflowRepository(session)
            record = WorkflowDefinitionRecord(
                id=new_id(),
                name="test-def",
                version=1,
                status=DefinitionStatus.DRAFT,
                graph_schema={"nodes": [], "edges": [], "entry_point": "x", "termination_points": []},
                tenant_id="tenant-a",
                created_by="tester",
            )
            created = await repo.create_definition(record)
            fetched = await repo.get_definition(created.id)
            assert fetched is not None
            assert fetched.name == "test-def"
            # A real JSONB round trip of a nested dict-of-lists — SQLite's JSON-as-TEXT
            # variant can silently get element type/order wrong in a way Postgres won't.
            assert fetched.graph_schema == record.graph_schema

            published = await repo.publish_definition(created.id)
            assert published.status == DefinitionStatus.PUBLISHED

            instance = WorkflowInstanceRecord(
                id=new_id(),
                definition_id=created.id,
                definition_version=1,
                tenant_id="tenant-a",
                trace_id="trace-xyz",
            )
            created_instance = await repo.create_instance(instance)
            fetched_instance = await repo.get_instance(created_instance.id)
            assert fetched_instance is not None
            assert fetched_instance.trace_id == "trace-xyz"
    finally:
        await engine.dispose()


async def test_get_definition_by_name_returns_highest_version_for_the_right_tenant(migrated_url):
    """Ticket #82: get_definition_by_name lets a caller (Conversational
    Engine's own settings.workflow_routing.definition_id, e.g.) resolve a
    definition by its stable name, set before the definition's
    server-generated id exists."""
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyWorkflowRepository(session)
            v1 = await repo.create_definition(
                WorkflowDefinitionRecord(
                    id=new_id(), name="support-agent-v1", version=1, status=DefinitionStatus.DRAFT,
                    graph_schema={"nodes": [], "edges": [], "entry_point": "x", "termination_points": []},
                    tenant_id="tenant-b", created_by="tester",
                )
            )
            v2 = await repo.create_definition(
                WorkflowDefinitionRecord(
                    id=new_id(), name="support-agent-v1", version=2, status=DefinitionStatus.DRAFT,
                    graph_schema={"nodes": [], "edges": [], "entry_point": "x", "termination_points": []},
                    tenant_id="tenant-b", created_by="tester",
                )
            )
            # A same-named definition for a different tenant must never be returned instead.
            await repo.create_definition(
                WorkflowDefinitionRecord(
                    id=new_id(), name="support-agent-v1", version=1, status=DefinitionStatus.DRAFT,
                    graph_schema={"nodes": [], "edges": [], "entry_point": "x", "termination_points": []},
                    tenant_id="tenant-other", created_by="tester",
                )
            )

            found = await repo.get_definition_by_name("support-agent-v1", "tenant-b")
            assert found is not None
            assert found.id == v2.id
            assert found.id != v1.id

            assert await repo.get_definition_by_name("no-such-name", "tenant-b") is None
    finally:
        await engine.dispose()
