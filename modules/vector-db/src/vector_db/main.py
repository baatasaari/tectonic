"""FastAPI application entrypoint (LLD §Level 4 "Deployment"). `/healthz`
checks Qdrant cluster health and LLM Gateway reachability.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text

from vector_db.api.routes_vectors import router as vectors_router
from vector_db.app_context import AppContext
from vector_db.clients.http_clients import HTTPEmbeddingProvider
from vector_db.clients.multi_tenancy_client import HTTPMultiTenancyClient
from vector_db.config import VectorDbSettings, load_settings
from vector_db.core.migration_manager import MigrationManager
from vector_db.core.vector_service import VectorService
from vector_db.db.repository import SQLAlchemyMigrationRepository
from vector_db.db.session import make_engine, make_session_factory
from vector_db.security.entitlement_gate import EntitlementGateMiddleware
from vector_db.security.jwt_auth import INSECURE_DEFAULT_SECRET, ServiceAuthMiddleware
from vector_db.security.openapi_security import configure_openapi_security
from vector_db.telemetry.logging import configure_logging, get_logger
from vector_db.telemetry.tracing import configure_tracing

logger = get_logger(component="main")


def build_app_context(settings: VectorDbSettings, *, qdrant_client: AsyncQdrantClient | None = None) -> AppContext:
    if qdrant_client is not None:
        client = qdrant_client
    elif settings.qdrant.embedded_in_memory:
        # Loud and unmissable, the same posture jwt_shared_secret_is_insecure_default
        # already takes: this must never be how a real deployment ends up running --
        # every point indexed is lost on the next restart.
        logger.warning(
            "qdrant_embedded_in_memory_mode",
            hint="set VECTOR_DB_QDRANT__EMBEDDED_IN_MEMORY=false and VECTOR_DB_QDRANT__URL "
            "to a real Qdrant cluster for any deployment where indexed data must survive a restart",
        )
        client = AsyncQdrantClient(location=":memory:")
    else:
        client = AsyncQdrantClient(url=settings.qdrant.url)

    engine = make_engine(settings)
    session_factory = make_session_factory(engine)

    embeddings = HTTPEmbeddingProvider(
        settings.llm_gateway_base_url, settings.qdrant.default_embedding_model,
        issuer=settings.service_name, shared_secret=settings.jwt_shared_secret, ttl_seconds=settings.jwt_ttl_seconds,
        default_virtual_key=settings.llm_gateway_virtual_key,
    )
    # A real, persistent migration repository -- Postgres-backed, not the in-memory
    # fake this module's own production wiring used to default to (independent
    # architecture assessment §10's other Vector DB finding: "migration state is in
    # memory"). See db/repository.py's own docstring for why this holds a
    # session_factory rather than a single shared session: it's called both from
    # request handlers and from the detached asyncio.create_task a migration run
    # starts, so it must be safe under concurrent, unrelated callers.
    migration_repository = SQLAlchemyMigrationRepository(session_factory)

    multi_tenancy = HTTPMultiTenancyClient(
        settings.multi_tenancy_base_url, issuer=settings.service_name, shared_secret=settings.jwt_shared_secret,
        ttl_seconds=settings.jwt_ttl_seconds,
    )

    vector_service = VectorService(
        client, embeddings, settings.qdrant.collection_alias, settings.isolation, settings.query,
        settings.qdrant.default_embedding_model, multi_tenancy=multi_tenancy,
    )
    migration_manager = MigrationManager(
        client, embeddings, migration_repository, settings.qdrant.collection_alias,
        settings.isolation.tenancy_model, settings.migration.batch_size, settings.migration.verification_sample_rate,
    )

    return AppContext(
        settings=settings, qdrant=client, engine=engine, session_factory=session_factory, embeddings=embeddings,
        migration_repository=migration_repository, vector_service=vector_service, migration_manager=migration_manager,
        multi_tenancy=multi_tenancy,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: VectorDbSettings = app.state.settings
    configure_logging(settings.telemetry.log_level)
    configure_tracing(settings.service_name, settings.telemetry.otlp_endpoint)

    if settings.jwt_shared_secret == INSECURE_DEFAULT_SECRET:
        logger.warning(
            "jwt_shared_secret_is_insecure_default",
            hint="set TECTONIC_JWT_SHARED_SECRET in every module sharing this deployment",
        )

    ctx = build_app_context(settings)
    app.state.ctx = ctx

    logger.info("startup_complete", service=settings.service_name, tenant_id=settings.tenant_id)
    try:
        yield
    finally:
        await ctx.qdrant.close()
        await ctx.engine.dispose()
        logger.info("shutdown_complete")


def create_app() -> FastAPI:
    settings = load_settings()

    app = FastAPI(
        title="Vector DB",
        version="0.1.0",
        description="Tectonic Agentic AI Platform — Module 10: hybrid dense-sparse embedding "
        "storage with automatic embedding model migration, backed by Qdrant.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        EntitlementGateMiddleware,
        module_name=settings.service_name,
        multi_tenancy_base_url=settings.multi_tenancy_base_url,
        issuer=settings.service_name,
        shared_secret=settings.jwt_shared_secret,
        cache_ttl_seconds=settings.entitlement_gate_cache_ttl_seconds,
    )
    app.add_middleware(
        ServiceAuthMiddleware, audience=settings.service_name, shared_secret=settings.jwt_shared_secret,
    )
    app.include_router(vectors_router)

    @app.get("/healthz")
    async def healthz() -> Response:
        ctx: AppContext = app.state.ctx
        components = {}
        components["qdrant"] = "ok" if await ctx.vector_service.cluster_healthy() else "degraded"
        try:
            async with ctx.session_factory() as session:
                await session.execute(text("SELECT 1"))
            components["postgres"] = "ok"
        except Exception as e:
            components["postgres"] = f"degraded: {e}"
        try:
            await ctx.embeddings.embed("healthcheck")
            components["llm_gateway"] = "ok"
        except Exception as e:
            components["llm_gateway"] = f"degraded: {e}"

        overall = "ok" if all(v == "ok" for v in components.values()) else "degraded"
        status_code = 200 if overall == "ok" else 503
        return Response(
            content=json.dumps({"status": overall, "components": components}),
            media_type="application/json",
            status_code=status_code,
        )

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    HTTPXClientInstrumentor().instrument()
    FastAPIInstrumentor.instrument_app(app)
    configure_openapi_security(app)
    return app


app = create_app()
