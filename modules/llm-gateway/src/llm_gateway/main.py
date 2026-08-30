"""FastAPI application entrypoint (LLD §Level 4 "Deployment"). Given this
module sits on the hot path for nearly every other module, `/healthz`
checks Redis, Postgres and provider reachability separately.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis
from sqlalchemy import text

from llm_gateway.api.routes_admin import router as admin_router
from llm_gateway.api.routes_completions import router as completions_router
from llm_gateway.app_context import AppContext
from llm_gateway.clients.http_clients import HTTPSecretsClient
from llm_gateway.clients.http_provider_client import HTTPProviderClient
from llm_gateway.clients.multi_tenancy_client import HTTPMultiTenancyClient
from llm_gateway.clients.redis_quality_scores import RedisQualityScoreProvider
from llm_gateway.config import LLMGatewaySettings, load_settings
from llm_gateway.core.semantic_cache import RedisSemanticCache
from llm_gateway.db.session import make_engine, make_session_factory
from llm_gateway.security.entitlement_gate import EntitlementGateMiddleware
from llm_gateway.security.jwt_auth import INSECURE_DEFAULT_SECRET, ServiceAuthMiddleware
from llm_gateway.security.openapi_security import configure_openapi_security
from llm_gateway.telemetry.logging import configure_logging, get_logger
from llm_gateway.telemetry.tracing import configure_tracing

logger = get_logger(component="main")


def build_app_context(settings: LLMGatewaySettings) -> AppContext:
    engine = make_engine(settings)
    redis = Redis.from_url(settings.redis_url)
    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        redis=redis,
        cache=RedisSemanticCache(redis, similarity_threshold=settings.cache.similarity_threshold),
        quality_scores=RedisQualityScoreProvider(redis),
        secrets=HTTPSecretsClient(
            settings.secrets_and_credential_management_base_url, issuer=settings.service_name,
            shared_secret=settings.jwt_shared_secret, ttl_seconds=settings.jwt_ttl_seconds,
        ),
        provider_client=HTTPProviderClient(providers={}),
        multi_tenancy=HTTPMultiTenancyClient(
            settings.multi_tenancy_base_url, issuer=settings.service_name,
            shared_secret=settings.jwt_shared_secret, ttl_seconds=settings.jwt_ttl_seconds,
        ),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: LLMGatewaySettings = app.state.settings
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
        await ctx.redis.aclose()
        await ctx.engine.dispose()
        logger.info("shutdown_complete")


def create_app() -> FastAPI:
    settings = load_settings()

    app = FastAPI(
        title="LLM Gateway",
        version="0.1.0",
        description="Tectonic Agentic AI Platform — Module 3: the only module permitted to call model "
        "providers directly. Quality-aware routing, semantic caching, cost governance, failover.",
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
    app.include_router(completions_router)
    app.include_router(admin_router)

    @app.get("/healthz")
    async def healthz() -> Response:
        ctx: AppContext = app.state.ctx
        components = {}
        try:
            async with ctx.session_factory() as session:
                await session.execute(text("SELECT 1"))
            components["postgres"] = "ok"
        except Exception as e:
            components["postgres"] = f"degraded: {e}"

        try:
            await ctx.redis.ping()
            components["redis"] = "ok"
        except Exception as e:
            components["redis"] = f"degraded: {e}"

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
