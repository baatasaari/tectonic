"""FastAPI application entrypoint (LLD §Level 4 "Deployment")."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from a2a_gateway.api.routes_a2a import router as a2a_router
from a2a_gateway.app_context import AppContext
from a2a_gateway.clients.a2a_peer_client import A2APeerHTTPClient
from a2a_gateway.clients.workflow_engine_client import WorkflowEngineHTTPClient
from a2a_gateway.config import A2AGatewaySettings, load_settings
from a2a_gateway.core.domain import card_to_dict
from a2a_gateway.core.local_card import build_local_card
from a2a_gateway.db.session import make_engine, make_session_factory
from a2a_gateway.security.entitlement_gate import EntitlementGateMiddleware
from a2a_gateway.security.jwt_auth import INSECURE_DEFAULT_SECRET, ServiceAuthMiddleware
from a2a_gateway.security.openapi_security import configure_openapi_security
from a2a_gateway.telemetry.logging import configure_logging, get_logger
from a2a_gateway.telemetry.tracing import configure_tracing

logger = get_logger(component="main")


def build_app_context(settings: A2AGatewaySettings) -> AppContext:
    engine = make_engine(settings)
    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        peer_client=A2APeerHTTPClient(),
        workflow_client=WorkflowEngineHTTPClient(
            settings.workflow_engine_base_url, issuer=settings.service_name, shared_secret=settings.jwt_shared_secret,
        ),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: A2AGatewaySettings = app.state.settings
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
        title="A2A",
        version="0.1.0",
        description="Tectonic Agentic AI Platform — Module 22: standardised agent-to-agent "
        "delegation and capability negotiation, cross-vendor federation over the A2A protocol.",
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
    app.include_router(a2a_router)

    @app.get("/.well-known/agent.json")
    async def agent_card() -> dict:
        return card_to_dict(build_local_card(settings))

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
