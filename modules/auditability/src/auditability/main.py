"""FastAPI application entrypoint (LLD §Level 4 "Deployment")."""
from __future__ import annotations

import asyncio
import contextlib
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from auditability.api.routes_auditability import router as auditability_router
from auditability.app_context import AppContext
from auditability.clients.http_clients import HTTPLLMGatewayClient
from auditability.config import AuditabilitySettings, load_settings
from auditability.core.audit_pack_worker import AuditPackWorker
from auditability.db.repository import SQLAlchemyAuditabilityRepository
from auditability.db.session import make_engine, make_session_factory
from auditability.security.jwt_auth import INSECURE_DEFAULT_SECRET, ServiceAuthMiddleware
from auditability.security.openapi_security import configure_openapi_security
from auditability.telemetry.logging import configure_logging, get_logger
from auditability.telemetry.tracing import configure_tracing

logger = get_logger(component="main")


def build_app_context(settings: AuditabilitySettings) -> AppContext:
    engine = make_engine(settings)
    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        llm_gateway=HTTPLLMGatewayClient(
            settings.llm_gateway_base_url, issuer=settings.service_name, shared_secret=settings.jwt_shared_secret,
            ttl_seconds=settings.jwt_ttl_seconds,
        ),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: AuditabilitySettings = app.state.settings
    configure_logging(settings.telemetry.log_level)
    configure_tracing(settings.service_name, settings.telemetry.otlp_endpoint)

    if settings.jwt_shared_secret == INSECURE_DEFAULT_SECRET:
        logger.warning(
            "jwt_shared_secret_is_insecure_default",
            hint="set TECTONIC_JWT_SHARED_SECRET in every module sharing this deployment",
        )

    ctx = build_app_context(settings)
    app.state.ctx = ctx

    @asynccontextmanager
    async def repository_factory():
        async with ctx.session_factory() as session:
            yield SQLAlchemyAuditabilityRepository(session)

    worker = AuditPackWorker(
        repository_factory, settings.audit_pack.output_format,
        poll_interval_seconds=settings.audit_pack.worker_poll_interval_seconds,
        lease_seconds=settings.audit_pack.worker_lease_seconds,
        max_attempts=settings.audit_pack.worker_max_attempts,
    )
    await worker.recover_stuck_packs()
    worker_task = asyncio.create_task(worker.run_forever())
    app.state.audit_pack_worker = worker

    logger.info(
        "startup_complete", service=settings.service_name, tenant_id=settings.tenant_id,
        audit_pack_worker_id=worker.worker_id,
    )
    try:
        yield
    finally:
        worker.stop()
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
        await ctx.engine.dispose()
        logger.info("shutdown_complete")


def create_app() -> FastAPI:
    settings = load_settings()

    app = FastAPI(
        title="Auditability",
        version="0.1.0",
        description="Tectonic Agentic AI Platform — Module 20: immutable, hash-chained event log "
        "with tamper-evidence, audit-pack export and natural-language query.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        ServiceAuthMiddleware, audience=settings.service_name, shared_secret=settings.jwt_shared_secret,
    )
    app.include_router(auditability_router)

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
