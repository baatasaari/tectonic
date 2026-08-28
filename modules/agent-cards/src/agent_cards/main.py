"""FastAPI application entrypoint (LLD §Level 4 "Deployment")."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from agent_cards.api.routes_agent_cards import router as agent_cards_router
from agent_cards.app_context import AppContext
from agent_cards.clients.evaluation_framework_client import HTTPEvaluationFrameworkClient
from agent_cards.clients.regulatory_compliance_client import HTTPRegulatoryComplianceClient
from agent_cards.config import AgentCardsSettings, load_settings
from agent_cards.db.session import make_engine, make_session_factory
from agent_cards.security.entitlement_gate import EntitlementGateMiddleware
from agent_cards.security.jwt_auth import INSECURE_DEFAULT_SECRET, ServiceAuthMiddleware
from agent_cards.security.openapi_security import configure_openapi_security
from agent_cards.telemetry.logging import configure_logging, get_logger
from agent_cards.telemetry.tracing import configure_tracing

logger = get_logger(component="main")


def build_app_context(settings: AgentCardsSettings) -> AppContext:
    engine = make_engine(settings)
    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        evaluation_framework=HTTPEvaluationFrameworkClient(
            settings.evaluation_framework_base_url, issuer=settings.service_name, shared_secret=settings.jwt_shared_secret,
        ),
        regulatory_compliance=HTTPRegulatoryComplianceClient(
            settings.regulatory_compliance_base_url, issuer=settings.service_name, shared_secret=settings.jwt_shared_secret,
        ),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: AgentCardsSettings = app.state.settings
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
        title="Agent Cards",
        version="0.1.0",
        description="Tectonic Agentic AI Platform — Module 23: trust-scored, machine-readable "
        "capability manifests for discovery.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    # Added in this order deliberately: Starlette's add_middleware makes the
    # most-recently-added middleware the outermost layer (it runs first), so adding
    # EntitlementGateMiddleware before ServiceAuthMiddleware means auth still runs
    # first on every request -- authenticate, then entitle.
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
    app.include_router(agent_cards_router)

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
