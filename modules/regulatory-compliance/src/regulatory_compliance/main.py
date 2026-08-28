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

from regulatory_compliance.api.routes_regcomp import router as regcomp_router
from regulatory_compliance.app_context import AppContext
from regulatory_compliance.clients.http_clients import HTTPAuditabilityClient
from regulatory_compliance.config import RegulatoryComplianceSettings, load_settings
from regulatory_compliance.core.evidence_worker import EvidencePackWorker
from regulatory_compliance.core.regulatory_feed import RegulatoryFeedManager
from regulatory_compliance.db.repository import SQLAlchemyRegulatoryComplianceRepository
from regulatory_compliance.db.session import make_engine, make_session_factory
from regulatory_compliance.security.entitlement_gate import EntitlementGateMiddleware
from regulatory_compliance.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
)
from regulatory_compliance.telemetry.logging import configure_logging, get_logger
from regulatory_compliance.telemetry.tracing import configure_tracing

logger = get_logger(component="main")


def build_app_context(settings: RegulatoryComplianceSettings) -> AppContext:
    engine = make_engine(settings)
    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        auditability=HTTPAuditabilityClient(
            settings.auditability_base_url, issuer=settings.service_name, shared_secret=settings.jwt_shared_secret,
            ttl_seconds=settings.jwt_ttl_seconds,
        ),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: RegulatoryComplianceSettings = app.state.settings
    configure_logging(settings.telemetry.log_level)
    configure_tracing(settings.service_name, settings.telemetry.otlp_endpoint)

    if settings.jwt_shared_secret == INSECURE_DEFAULT_SECRET:
        logger.warning(
            "jwt_shared_secret_is_insecure_default",
            hint="set TECTONIC_JWT_SHARED_SECRET in every module sharing this deployment",
        )

    ctx = build_app_context(settings)
    app.state.ctx = ctx

    async with ctx.session_factory() as session:
        repository = SQLAlchemyRegulatoryComplianceRepository(session)
        seeded = await RegulatoryFeedManager(repository).seed_defaults()
        logger.info("crosswalk_table_seeded", mappings=seeded)

    @asynccontextmanager
    async def repository_factory():
        async with ctx.session_factory() as session:
            yield SQLAlchemyRegulatoryComplianceRepository(session)

    worker = EvidencePackWorker(
        repository_factory, ctx.auditability, settings.evidence.output_format,
        poll_interval_seconds=settings.evidence.worker_poll_interval_seconds,
        lease_seconds=settings.evidence.worker_lease_seconds,
        max_attempts=settings.evidence.worker_max_attempts,
    )
    await worker.recover_stuck_packs()
    worker_task = asyncio.create_task(worker.run_forever())
    app.state.evidence_worker = worker

    logger.info(
        "startup_complete", service=settings.service_name, tenant_id=settings.tenant_id,
        evidence_worker_id=worker.worker_id,
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
        title="Regulatory and Compliance",
        version="0.1.0",
        description="Tectonic Agentic AI Platform — Module 17: crosswalk engine mapping controls "
        "once to EU AI Act, NIST AI RMF, ISO 42001 and DORA, with living regulatory feed.",
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
    app.include_router(regcomp_router)

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
