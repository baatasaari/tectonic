"""FastAPI application entrypoint (LLD §Level 4 "Deployment"). `/healthz`
checks Postgres and configured notification channel reachability.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from human_oversight.api.routes_oversight import router as oversight_router
from human_oversight.app_context import AppContext
from human_oversight.clients.http_clients import (
    HTTPAuditabilityClient,
    HTTPDecisionCallbackDispatcher,
    SlackNotificationChannel,
    SMTPNotificationChannel,
    TeamsNotificationChannel,
    WebhookNotificationChannel,
)
from human_oversight.config import HumanOversightSettings, load_settings
from human_oversight.db.session import make_engine, make_session_factory
from human_oversight.security.jwt_auth import INSECURE_DEFAULT_SECRET, ServiceAuthMiddleware
from human_oversight.telemetry.logging import configure_logging, get_logger
from human_oversight.telemetry.tracing import configure_tracing

logger = get_logger(component="main")


def build_app_context(settings: HumanOversightSettings) -> AppContext:
    engine = make_engine(settings)
    auth_kwargs = {
        "issuer": settings.service_name, "shared_secret": settings.jwt_shared_secret,
        "ttl_seconds": settings.jwt_ttl_seconds,
    }

    channels = {
        "slack": SlackNotificationChannel(f"{settings.notification_stub_base_url}/v1/notifications/slack"),
        "teams": TeamsNotificationChannel(f"{settings.notification_stub_base_url}/v1/notifications/teams"),
        "webhook": WebhookNotificationChannel(f"{settings.notification_stub_base_url}/v1/notifications/webhook"),
        # Real SMTP code path, not exercised in this build's stub-based
        # tests — see the module README.
        "email": SMTPNotificationChannel("localhost", 25, "oversight@tectonic.local", "reviewers@tectonic.local"),
    }

    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        notification_channels=channels,
        callback_dispatcher=HTTPDecisionCallbackDispatcher(settings.service_urls, **auth_kwargs),
        auditability=HTTPAuditabilityClient(settings.auditability_base_url, **auth_kwargs),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: HumanOversightSettings = app.state.settings
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
        title="Human Oversight",
        version="0.1.0",
        description="Tectonic Agentic AI Platform — Module 16: designed-in approval queues, "
        "override logging, escalation routing per EU AI Act Article 14.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        ServiceAuthMiddleware, audience=settings.service_name, shared_secret=settings.jwt_shared_secret,
    )
    app.include_router(oversight_router)

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
