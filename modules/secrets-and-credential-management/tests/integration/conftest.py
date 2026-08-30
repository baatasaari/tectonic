"""Shared fixture for the Postgres integration tier (this platform's
now-standard pattern -- see the module README's "Design notes vs. the
LLD").

Two ways to get a real Postgres, tried in order:

1. `TECTONIC_TEST_POSTGRES_URL` set to an admin connection string for an
   already-running Postgres (a CI service container, a local `postgresql`
   install) — this fixture creates and drops a fresh, isolated database
   per test-module run against it. Useful in any environment where Docker
   itself isn't available (or isn't wanted) but a real Postgres is.
2. Left unset, with a Docker daemon available: `testcontainers` spins up a
   disposable `postgres:16-alpine` container instead — the zero-config
   default for CI runners and local dev with Docker.

Neither available -> the whole integration tier is skipped, not failed;
this tier is intentionally not part of the default `pytest` run.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import uuid

import pytest
import pytest_asyncio

pytestmark = pytest.mark.integration


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=5, check=True)
        return True
    except Exception:
        return False


def _external_admin_url() -> str | None:
    return os.environ.get("TECTONIC_TEST_POSTGRES_URL")


if _external_admin_url() is None:
    pytest.importorskip("testcontainers")
    if not _docker_available():
        pytest.skip("Neither TECTONIC_TEST_POSTGRES_URL nor a Docker daemon is available", allow_module_level=True)


@pytest_asyncio.fixture(scope="module")
async def postgres_url():
    import asyncpg

    external = _external_admin_url()
    if external:
        db_name = f"test_{uuid.uuid4().hex[:12]}"
        # asyncpg.connect() takes any postgresql:// DSN regardless of SQLAlchemy driver
        # suffix; strip one off if present so this doesn't choke on it.
        asyncpg_dsn = external.replace("postgresql+asyncpg://", "postgresql://", 1)
        conn = await asyncpg.connect(asyncpg_dsn)
        try:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
        finally:
            await conn.close()

        # SQLAlchemy needs the +asyncpg driver marker explicitly — a bare postgresql://
        # resolves to the sync psycopg2 dialect, which isn't even installed here.
        base = asyncpg_dsn.replace("postgresql://", "postgresql+asyncpg://", 1).rsplit("/", 1)[0]
        url = f"{base}/{db_name}"
        try:
            yield url
        finally:
            conn = await asyncpg.connect(asyncpg_dsn)
            try:
                await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
            finally:
                await conn.close()
        return

    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url().replace("psycopg2", "asyncpg")
