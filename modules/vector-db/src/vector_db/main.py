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

from vector_db.api.routes_vectors import router as vectors_router
from vector_db.app_context import AppContext
from vector_db.clients.http_clients import HTTPEmbeddingProvider
from vector_db.config import VectorDbSettings, load_settings
from vector_db.core.fakes import InMemoryMigrationRepository
from vector_db.core.migration_manager import MigrationManager
from vector_db.core.vector_service import VectorService
from vector_db.security.entitlement_gate import EntitlementGateMiddleware
from vector_db.security.jwt_auth import INSECURE_DEFAULT_SECRET, ServiceAuthMiddleware
from vector_db.telemetry.logging import configure_logging, get_logger
from vector_db.telemetry.tracing import configure_tracing

logger = get_logger(component="main")


def build_app_context(settings: VectorDbSettings, *, qdrant_client: AsyncQdrantClient | None = None) -> AppContext:
    client = qdrant_client or (
        AsyncQdrantClient(url=settings.qdrant.url) if settings.qdrant.url else AsyncQdrantClient(location=":memory:")
    )
    embeddings = HTTPEmbeddingProvider(
        settings.llm_gateway_base_url, settings.qdrant.default_embedding_model,
        issuer=settings.service_name, shared_secret=settings.jwt_shared_secret, ttl_seconds=settings.jwt_ttl_seconds,
    )
    migration_repository = InMemoryMigrationRepository()

    vector_service = VectorService(
        client, embeddings, settings.qdrant.collection_alias, settings.isolation, settings.query,
        settings.qdrant.default_embedding_model,
    )
    migration_manager = MigrationManager(
        client, embeddings, migration_repository, settings.qdrant.collection_alias,
        settings.isolation.tenancy_model, settings.migration.batch_size, settings.migration.verification_sample_rate,
    )

    return AppContext(
        settings=settings, qdrant=client, embeddings=embeddings, migration_repository=migration_repository,
        vector_service=vector_service, migration_manager=migration_manager,
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
    return app


app = create_app()
