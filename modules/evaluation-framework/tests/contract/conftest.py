"""Shared fixture for the contract-test tier (mechanical-leverage backlog
item: continuing ticket #73/#80's rollout, this time to Evaluation
Framework -- real OpenAPI-schema-driven fuzzing against this module's own
real, running app, not just an installed-but-unused `schemathesis` dev
dependency). Picked for this rollout specifically because this session's
own evaluation-gated-release-path work just added a new, never-fuzzed
route (`GET /eval-runs`) and made this module's `/gate` verdict load-
bearing for both PromptOps' and LLMOps' own release gates -- a bug here
now has a wider blast radius than before. Reuses the exact same
real-Postgres provisioning logic `tests/integration/conftest.py` already
established for this module -- see that file's own docstring for the two
ways a real Postgres gets obtained, and why neither available means this
tier skips rather than fails.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import uuid

import pytest
import pytest_asyncio

pytestmark = pytest.mark.contract


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
        db_name = f"contract_{uuid.uuid4().hex[:12]}"
        asyncpg_dsn = external.replace("postgresql+asyncpg://", "postgresql://", 1)
        conn = await asyncpg.connect(asyncpg_dsn)
        try:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
        finally:
            await conn.close()

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


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    from alembic.config import Config as AlembicConfig

    from alembic import command

    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["EVALUATION_FRAMEWORK_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


@pytest.fixture(scope="module")
def contract_app(migrated_url):
    """A real app instance, wired against the freshly-migrated test
    Postgres, with `app.state.ctx` set the same way the real `lifespan`
    context manager would -- set directly rather than entering that
    context manager. This module's own real `lifespan` has no
    background-worker side effects (no Kafka producer/outbox relay); the
    LLM Gateway client's `httpx.AsyncClient` and the DB engine are both
    lazy, nothing opens a real connection at construction time -- but the
    lifespan is still swapped for a no-op here for the same reason every
    other module's contract conftest.py does: schemathesis's ASGI
    transport does drive the ASGI lifespan protocol regardless of whether
    a given module's own lifespan has anything worth avoiding."""
    from contextlib import asynccontextmanager

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from evaluation_framework.main import build_app_context, create_app

    app = create_app()

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    app.router.lifespan_context = _noop_lifespan

    ctx = build_app_context(app.state.settings)

    # schemathesis's synchronous `case.call()` bridges into the ASGI app through a
    # fresh event loop per call (httpx's ASGI transport, not this test process's own
    # pytest-asyncio loop) -- a pooled AsyncEngine's asyncpg connections are bound to
    # whichever loop created them, so reusing build_app_context's own pooled engine
    # across calls leaks a connection every call, exhausting Postgres's
    # max_connections within one contract-test run. NullPool sidesteps this the
    # standard way: every checkout opens a genuinely new physical connection and
    # closes it again on checkin, so nothing is ever handed back to a now-dead loop.
    ctx.engine = create_async_engine(app.state.settings.database_url, poolclass=NullPool)
    ctx.session_factory = async_sessionmaker(ctx.engine, expire_on_commit=False)

    app.state.ctx = ctx
    return app


@pytest.fixture(scope="module")
def auth_headers(contract_app):
    """A valid service-to-service bearer token, scoped to this module's
    own audience -- every route this module serves sits behind
    `ServiceAuthMiddleware`'s zero-trust check (only `/healthz`/`/metrics`
    excluded), `/openapi.json` itself included."""
    from evaluation_framework.security.jwt_auth import mint_service_token

    settings = contract_app.state.settings
    token = mint_service_token(
        issuer="contract-test", audience=settings.service_name, shared_secret=settings.jwt_shared_secret,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def api_schema(contract_app, auth_headers):
    """The real OpenAPI schema this app itself generates
    (`security/openapi_security.py`), loaded directly against the real
    ASGI app -- every request schemathesis makes goes through the real
    middleware stack (`ServiceAuthMiddleware`, `EntitlementGateMiddleware`)
    and real route handlers, not a mocked transport. `headers` here
    authenticates the schema *fetch* itself; `test_openapi_contract.py`
    passes the same headers again on every generated operation call.
    `EntitlementGateMiddleware` fails open when Multi-tenancy is
    unreachable (this module's own documented posture), so it never blocks
    fuzzing here even with no real Multi-tenancy running."""
    import schemathesis

    schema = schemathesis.openapi.from_asgi("/openapi.json", contract_app, headers=auth_headers)
    # /healthz and /metrics are cluster-internal diagnostic endpoints (the same
    # _EXCLUDED_PATHS this module's own jwt_auth.py already carves out of auth), not
    # part of this module's real API contract -- /metrics in particular returns
    # real Prometheus text exposition, not JSON, which FastAPI's own default OpenAPI
    # generation has no way to declare without every module hand-annotating a
    # non-default response content-type on a route nothing calls as an API.
    return schema.exclude(path=["/healthz", "/metrics"])
