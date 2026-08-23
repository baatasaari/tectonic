"""Integration tier (LLD §4.8): the SQLAlchemy repository against a real
Postgres, via testcontainers. Not part of the default unit-test run — this
tier needs a Docker daemon, which the sandbox this module was scaffolded in
does not have; it runs in CI or any environment with Docker available.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

pytestmark = pytest.mark.asyncio


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=5, check=True)
        return True
    except Exception:
        return False


pytest.importorskip("testcontainers")

if not _docker_available():
    pytest.skip("Docker daemon not available", allow_module_level=True)

from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from alembic import command
from workflow_engine.core.domain import (
    DefinitionStatus,
    WorkflowDefinitionRecord,
    WorkflowInstanceRecord,
    new_id,
)
from workflow_engine.db.repository import SQLAlchemyWorkflowRepository


@pytest.fixture(scope="module")
def postgres_url():
    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url().replace("psycopg2", "asyncpg")

        alembic_cfg = AlembicConfig("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", url)
        import os

        os.environ["WORKFLOW_ENGINE_DATABASE_URL"] = url
        command.upgrade(alembic_cfg, "head")

        yield url


async def test_create_and_fetch_definition_round_trips(postgres_url):
    engine = create_async_engine(postgres_url)
    async with engine.connect() as conn:
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(conn) as session:
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
    await engine.dispose()
