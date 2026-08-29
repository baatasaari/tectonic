"""Shared fixture for the contract-test tier (Phase 1 gap: rollout of
Billing and Metering's own reference implementation, ticket #73/#80,
to a fourth module -- real OpenAPI-schema-driven fuzzing against this
module's own real, running app, not just an installed-but-unused
`schemathesis` dev dependency). Reuses the exact same real-Postgres
provisioning logic `tests/integration/conftest.py` already established
for this module -- see that file's own docstring for the two ways a
real Postgres gets obtained, and why neither available means this tier
skips rather than fails.
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
    os.environ["VECTOR_DB_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


@pytest.fixture(scope="module")
def contract_app(migrated_url):
    """A real app instance, wired against the freshly-migrated test
    Postgres, with `app.state.ctx` set the same way the real `lifespan`
    context manager would -- set directly rather than entering that
    context manager, since schemathesis's ASGI transport doesn't drive
    FastAPI's lifespan events itself.

    Qdrant runs embedded in-memory here (`build_app_context`'s own
    `qdrant_client` override, the same testability hook this module's
    own unit-test harness already uses) rather than against
    `settings.qdrant.url`'s real-cluster default (ticket #66's own
    fix) -- a contract-test run must never depend on a real Qdrant
    cluster being reachable. `embeddings` and `multi_tenancy` are
    likewise swapped for this module's own `core/fakes.py` stubs
    (`StubEmbeddingProvider`/`StubMultiTenancyQuotaClient`): this
    module's own `index_point` genuinely needs LLM Gateway reachable
    to embed content with no vector supplied, and genuinely calls
    Multi-tenancy's quota/check pre-flight (ticket #78) -- neither
    peer being unreachable is an *input-validation* contract this tier
    is meant to prove, and hammering both with retried real network
    calls on every fuzzed request made this tier minutes slower for no
    signal (found running this tier for real)."""
    from contextlib import asynccontextmanager

    from qdrant_client import AsyncQdrantClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from vector_db.core.fakes import StubEmbeddingProvider, StubMultiTenancyQuotaClient
    from vector_db.core.migration_manager import MigrationManager
    from vector_db.core.vector_service import VectorService
    from vector_db.db.repository import SQLAlchemyMigrationRepository
    from vector_db.main import build_app_context, create_app

    app = create_app()

    # schemathesis's ASGI transport DOES drive the ASGI lifespan protocol -- the real
    # `lifespan()` would otherwise overwrite app.state.ctx with its own freshly-built,
    # non-stubbed context (a real AsyncQdrantClient against settings.qdrant.url,
    # unreachable here) on every single case.call(), silently undoing everything this
    # fixture sets up below. Swapped for a no-op before use, the same fix Workflow
    # Engine's and Multi-tenancy's own contract conftest.py apply for the identical
    # reason (found running this tier for real).
    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    app.router.lifespan_context = _noop_lifespan

    ctx = build_app_context(app.state.settings, qdrant_client=AsyncQdrantClient(location=":memory:"))
    settings = app.state.settings

    # schemathesis's synchronous `case.call()` bridges into the ASGI app through a
    # fresh event loop per call (httpx's ASGI transport, not this test process's own
    # pytest-asyncio loop) -- a pooled AsyncEngine's asyncpg connections are bound to
    # whichever loop created them, so reusing build_app_context's own pooled engine
    # (`pool_pre_ping=True` besides) across calls leaks a connection every call and
    # crashes `do_ping`'s own cross-loop query with a raw asyncpg RuntimeError,
    # exhausting Postgres's max_connections within one contract-test run. NullPool
    # sidesteps this the standard way: every checkout opens a genuinely new physical
    # connection and closes it again on checkin, so nothing is ever handed back to a
    # now-dead loop.
    ctx.engine = create_async_engine(settings.database_url, poolclass=NullPool)
    ctx.session_factory = async_sessionmaker(ctx.engine, expire_on_commit=False)

    # VectorService/MigrationManager/the migration repository itself all capture
    # their own dependencies at construction time (build_app_context's own, real
    # ones -- the pooled session_factory just replaced above included, since
    # migration_repository is built from it too) -- overwriting ctx.embeddings/
    # ctx.multi_tenancy/ctx.session_factory alone wouldn't reach any of them, so all
    # three are rebuilt here against the stubs and the NullPool session_factory.
    ctx.embeddings = StubEmbeddingProvider()
    ctx.multi_tenancy = StubMultiTenancyQuotaClient()
    ctx.migration_repository = SQLAlchemyMigrationRepository(ctx.session_factory)
    ctx.vector_service = VectorService(
        ctx.qdrant, ctx.embeddings, settings.qdrant.collection_alias, settings.isolation, settings.query,
        settings.qdrant.default_embedding_model, multi_tenancy=ctx.multi_tenancy,
    )
    ctx.migration_manager = MigrationManager(
        ctx.qdrant, ctx.embeddings, ctx.migration_repository, settings.qdrant.collection_alias,
        settings.isolation.tenancy_model, settings.migration.batch_size, settings.migration.verification_sample_rate,
    )

    # POST /migrations fires a detached `asyncio.create_task` for the real migration
    # run (api/routes_vectors.py's own `_run_migration_in_background`) -- correct,
    # intentional production behavior (a real background job outliving the request),
    # but schemathesis's synchronous `case.call()` runs each request through its own
    # short-lived event loop (the same one NullPool works around above); a background
    # task that outlives that loop's teardown hits genuine asyncio/asyncpg "attached
    # to a different loop" errors from a harness artifact, not from anything this
    # endpoint's own request/response input validation does wrong -- confirmed by
    # Hypothesis's own FlakyFailure (fails on first call, not on replay) rather than a
    # reliably-reproducible case (found running this tier for real). Started
    # migration runs themselves are already covered for real by this module's own
    # `tests/unit/test_migration_manager.py` and `tests/integration` tiers; this tier
    # proves the request/response contract, the same scope `/healthz`/`/metrics`'s own
    # exclusion below already draws the line at.
    import vector_db.api.routes_vectors as routes_vectors_module

    def _skip_background_migration(_ctx, _migration_id):
        return None

    routes_vectors_module._run_migration_in_background = _skip_background_migration

    app.state.ctx = ctx
    return app


@pytest.fixture(scope="module")
def auth_headers(contract_app):
    """A valid service-to-service bearer token, scoped to this module's
    own audience -- every route this module serves, `/openapi.json`
    itself included (`ServiceAuthMiddleware` excludes only `/healthz`/
    `/metrics`, a deliberately zero-trust posture: this module's API
    shape isn't handed out unauthenticated either), sits behind it."""
    from vector_db.security.jwt_auth import mint_service_token

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
    passes the same headers again on every generated operation call."""
    import schemathesis

    schema = schemathesis.openapi.from_asgi("/openapi.json", contract_app, headers=auth_headers)
    # /healthz and /metrics are cluster-internal diagnostic endpoints (the same
    # _EXCLUDED_PATHS this module's own jwt_auth.py already carves out of auth), not
    # part of this module's real API contract -- /metrics in particular returns
    # real Prometheus text exposition, not JSON, which FastAPI's own default OpenAPI
    # generation has no way to declare without every module hand-annotating a
    # non-default response content-type on a route nothing calls as an API.
    return schema.exclude(path=["/healthz", "/metrics"])
