"""FastAPI application entrypoint (LLD §Level 4 "Deployment"). `/healthz`
checks Postgres, Vector DB and Graph DB reachability.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from long_term_memory.api.routes_memory import router as memory_router
from long_term_memory.app_context import AppContext
from long_term_memory.clients.http_clients import (
    HTTPGraphDBClient,
    HTTPGuardrailsClient,
    HTTPLLMGatewayClient,
    HTTPVectorDBClient,
)
from long_term_memory.config import LongTermMemorySettings, load_settings
from long_term_memory.db.session import make_engine, make_session_factory
from long_term_memory.telemetry.logging import configure_logging, get_logger
from long_term_memory.telemetry.tracing import configure_tracing

logger = get_logger(component="main")


def build_app_context(settings: LongTermMemorySettings) -> AppContext:
    engine = make_engine(settings)
    dep_url = settings.dependency_stub_base_url
    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        vector_db=HTTPVectorDBClient(dep_url),
        graph_db=HTTPGraphDBClient(dep_url),
        llm_gateway=HTTPLLMGatewayClient(dep_url),
        guardrails=HTTPGuardrailsClient(dep_url),
    )


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
        await ctx.engine.dispose()
        logger.info("shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Long-Term Memory",
        version="0.1.0",
        description="Tectonic Agentic AI Platform — Module 13: durable, cross-session hybrid "
        "memory store with consolidation, forgetting and self-reflection.",
        lifespan=lifespan,
    )
    app.include_router(memory_router)

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
