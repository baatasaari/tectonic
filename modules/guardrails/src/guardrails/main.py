"""FastAPI application entrypoint (LLD §Level 4 "Deployment")."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from guardrails.api.routes_guardrails import router as guardrails_router
from guardrails.app_context import AppContext
from guardrails.clients.http_clients import HTTPLLMGatewayClient, HTTPSentinelAgentsClient
from guardrails.config import GuardrailsSettings, load_settings
from guardrails.db.session import make_engine, make_session_factory
from guardrails.telemetry.logging import configure_logging, get_logger
from guardrails.telemetry.tracing import configure_tracing

logger = get_logger(component="main")


def build_app_context(settings: GuardrailsSettings) -> AppContext:
    engine = make_engine(settings)
    dep_url = settings.dependency_stub_base_url
    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        llm_gateway=HTTPLLMGatewayClient(dep_url),
        sentinel_agents=HTTPSentinelAgentsClient(dep_url),
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
        title="Guardrails",
        version="0.1.0",
        description="Tectonic Agentic AI Platform — Module 14: dual-stage input/output policy "
        "enforcement for every LLM Gateway call.",
        lifespan=lifespan,
    )
    app.include_router(guardrails_router)

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
