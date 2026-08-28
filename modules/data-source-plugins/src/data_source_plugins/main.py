"""FastAPI application entrypoint (LLD §Level 4 "Deployment"). `/healthz`
checks Postgres and Secrets and Credential Management reachability.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from data_source_plugins.api.routes_connectors import router as connectors_router
from data_source_plugins.app_context import AppContext
from data_source_plugins.clients.http_clients import HTTPSecretsClient, HTTPSourceConnectorRuntime
from data_source_plugins.config import DataSourcePluginsSettings, load_settings
from data_source_plugins.db.session import make_engine, make_session_factory
from data_source_plugins.security.entitlement_gate import EntitlementGateMiddleware
from data_source_plugins.security.jwt_auth import INSECURE_DEFAULT_SECRET, ServiceAuthMiddleware
from data_source_plugins.telemetry.logging import configure_logging, get_logger
from data_source_plugins.telemetry.tracing import configure_tracing

logger = get_logger(component="main")


def build_app_context(settings: DataSourcePluginsSettings) -> AppContext:
    engine = make_engine(settings)
    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        # HTTPSourceConnectorRuntime deliberately excluded from service-to-service JWT
        # auth -- see the comment on that class in clients/http_clients.py.
        connector_runtime=HTTPSourceConnectorRuntime(settings.secrets_and_credential_management_base_url),
        secrets_client=HTTPSecretsClient(
            settings.secrets_and_credential_management_base_url, issuer=settings.service_name,
            shared_secret=settings.jwt_shared_secret, ttl_seconds=settings.jwt_ttl_seconds,
        ),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: DataSourcePluginsSettings = app.state.settings
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
        title="Data Source Plugins",
        version="0.1.0",
        description="Tectonic Agentic AI Platform — Module 8: connectivity to external data "
        "systems with schema drift auto-adaptation and data quality scoring.",
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
    app.include_router(connectors_router)

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
            await ctx.secrets_client.resolve("healthcheck")
            components["secrets"] = "ok"
        except Exception as e:
            components["secrets"] = f"degraded: {e}"

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
