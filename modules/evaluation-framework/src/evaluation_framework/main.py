"""FastAPI application entrypoint (LLD §Level 4 "Deployment")."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from evaluation_framework.api.routes_evalfw import router as evalfw_router
from evaluation_framework.app_context import AppContext
from evaluation_framework.clients.http_clients import HTTPLLMGatewayClient
from evaluation_framework.config import EvaluationFrameworkSettings, load_settings
from evaluation_framework.core.sampler import ProductionSampler
from evaluation_framework.db.session import make_engine, make_session_factory
from evaluation_framework.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
)
from evaluation_framework.telemetry.logging import configure_logging, get_logger
from evaluation_framework.telemetry.tracing import configure_tracing

logger = get_logger(component="main")


def build_app_context(settings: EvaluationFrameworkSettings) -> AppContext:
    engine = make_engine(settings)
    dep_url = settings.dependency_stub_base_url
    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        llm_gateway=HTTPLLMGatewayClient(
            dep_url, issuer=settings.service_name, shared_secret=settings.jwt_shared_secret,
            ttl_seconds=settings.jwt_ttl_seconds,
        ),
        sampler=ProductionSampler(settings.production_sampling.sample_rate),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: EvaluationFrameworkSettings = app.state.settings
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
        await ctx.engine.dispose()
        logger.info("shutdown_complete")


def create_app() -> FastAPI:
    settings = load_settings()

    app = FastAPI(
        title="Evaluation Framework",
        version="0.1.0",
        description="Tectonic Agentic AI Platform — Module 18: faithfulness, coherence and "
        "tool-trace scoring, as both a CI/CD gate and continuous production evaluation.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        ServiceAuthMiddleware, audience=settings.service_name, shared_secret=settings.jwt_shared_secret,
    )
    app.include_router(evalfw_router)

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

    HTTPXClientInstrumentor().instrument()
    FastAPIInstrumentor.instrument_app(app)
    return app


app = create_app()
