"""FastAPI application entrypoint (LLD §Level 4 "Deployment")."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from deployment_strategy.api.routes_deployment_strategy import router as deployment_strategy_router
from deployment_strategy.app_context import AppContext
from deployment_strategy.clients.evaluation_framework_client import HTTPEvaluationFrameworkClient
from deployment_strategy.clients.finops_client import HTTPFinOpsClient
from deployment_strategy.config import DeploymentStrategySettings, load_settings
from deployment_strategy.db.session import make_engine, make_session_factory
from deployment_strategy.security.entitlement_gate import EntitlementGateMiddleware
from deployment_strategy.security.jwt_auth import INSECURE_DEFAULT_SECRET, ServiceAuthMiddleware
from deployment_strategy.security.openapi_security import configure_openapi_security
from deployment_strategy.telemetry.logging import configure_logging, get_logger
from deployment_strategy.telemetry.tracing import configure_tracing

logger = get_logger(component="main")


def build_app_context(settings: DeploymentStrategySettings) -> AppContext:
    engine = make_engine(settings)
    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        evaluation_framework=HTTPEvaluationFrameworkClient(
            settings.evaluation_framework_base_url, issuer=settings.service_name, shared_secret=settings.jwt_shared_secret,
        ),
        finops=HTTPFinOpsClient(
            settings.finops_base_url, issuer=settings.service_name, shared_secret=settings.jwt_shared_secret,
        ),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: DeploymentStrategySettings = app.state.settings
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
        title="Deployment Strategy",
        version="0.1.0",
        description="Tectonic Agentic AI Platform — Module 27: cloud-agnostic packaging with "
        "agent-aware canary analysis, gated by real Evaluation Framework and FinOps signals.",
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
    app.include_router(deployment_strategy_router)

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
