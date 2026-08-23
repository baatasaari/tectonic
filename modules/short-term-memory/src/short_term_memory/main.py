"""FastAPI application entrypoint (LLD §Level 4 "Deployment"). Stateless
API layer, Redis as the only stateful dependency.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis

from short_term_memory.api.routes_sessions import router as sessions_router
from short_term_memory.app_context import AppContext
from short_term_memory.clients.http_clients import HTTPLLMGatewayClient
from short_term_memory.clients.redis_buffer_store import RedisBufferStore
from short_term_memory.config import ShortTermMemorySettings, load_settings
from short_term_memory.core.buffer_manager import BufferManager
from short_term_memory.telemetry.logging import configure_logging, get_logger
from short_term_memory.telemetry.tracing import configure_tracing

logger = get_logger(component="main")


def build_app_context(settings: ShortTermMemorySettings, *, redis: Redis | None = None) -> AppContext:
    redis = redis or Redis.from_url(settings.redis_url)
    buffer_manager = BufferManager(
        RedisBufferStore(redis), HTTPLLMGatewayClient(settings.dependency_stub_base_url),
        settings.buffer, settings.salience,
    )
    return AppContext(settings=settings, redis=redis, buffer_manager=buffer_manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    configure_logging(settings.telemetry.log_level)
    configure_tracing(settings.service_name, settings.telemetry.otlp_endpoint)

    ctx = build_app_context(settings)
    app.state.ctx = ctx

    logger.info("startup_complete", service=settings.service_name, tenant_id=settings.tenant_id)
    try:
        yield
    finally:
        await ctx.redis.aclose()
        logger.info("shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Short-Term Memory",
        version="0.1.0",
        description="Tectonic Agentic AI Platform — Module 12: token-budgeted session buffer "
        "with salience-weighted retention.",
        lifespan=lifespan,
    )
    app.include_router(sessions_router)

    @app.get("/healthz")
    async def healthz() -> Response:
        ctx: AppContext = app.state.ctx
        components = {}
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

    FastAPIInstrumentor.instrument_app(app)
    return app


app = create_app()
