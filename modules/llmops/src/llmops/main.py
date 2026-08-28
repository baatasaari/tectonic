"""FastAPI application entrypoint (LLD §Level 4 "Deployment")."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from llmops.api.routes_llmops import router as llmops_router
from llmops.app_context import AppContext
from llmops.clients.evaluation_framework_client import HTTPEvaluationFrameworkClient
from llmops.config import LLMOpsSettings, load_settings
from llmops.db.session import make_engine, make_session_factory
from llmops.security.entitlement_gate import EntitlementGateMiddleware
from llmops.security.jwt_auth import INSECURE_DEFAULT_SECRET, ServiceAuthMiddleware
from llmops.security.openapi_security import configure_openapi_security
from llmops.telemetry.logging import configure_logging, get_logger
from llmops.telemetry.tracing import configure_tracing

logger = get_logger(component="main")


def build_app_context(settings: LLMOpsSettings) -> AppContext:
    engine = make_engine(settings)
    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        evaluation_framework=HTTPEvaluationFrameworkClient(
            settings.evaluation_framework_base_url, issuer=settings.service_name, shared_secret=settings.jwt_shared_secret,
        ),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: LLMOpsSettings = app.state.settings
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
        title="LLMOps",
        version="0.1.0",
        description="Tectonic Agentic AI Platform — Module 25: model registry, versioning, "
        "staged rollout and automatic canary evaluation gated by real Evaluation Framework scores.",
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
    app.include_router(llmops_router)

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
    configure_openapi_security(app)
    return app


app = create_app()
