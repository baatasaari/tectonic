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

from multi_tenancy.api.routes_multi_tenancy import router as multi_tenancy_router
from multi_tenancy.app_context import AppContext
from multi_tenancy.clients.auditability_client import HTTPAuditabilityClient
from multi_tenancy.clients.kafka_publisher import KafkaEventPublisher
from multi_tenancy.clients.tenant_scoped_list_client import HTTPTenantScopedListClient
from multi_tenancy.config import MultiTenancySettings, load_settings
from multi_tenancy.core.outbox_worker import OutboxRelayWorker
from multi_tenancy.db.repository import SQLAlchemyMultiTenancyRepository
from multi_tenancy.db.session import make_engine, make_session_factory
from multi_tenancy.security.jwt_auth import INSECURE_DEFAULT_SECRET, ServiceAuthMiddleware
from multi_tenancy.security.openapi_security import configure_openapi_security
from multi_tenancy.telemetry.logging import configure_logging, get_logger
from multi_tenancy.telemetry.tracing import configure_tracing

logger = get_logger(component="main")


def build_app_context(settings: MultiTenancySettings) -> tuple[AppContext, KafkaEventPublisher]:
    engine = make_engine(settings)
    probe_clients = {
        target.name: HTTPTenantScopedListClient(
            target.base_url, target.list_path, issuer=settings.service_name,
            shared_secret=settings.jwt_shared_secret, audience=target.audience,
        )
        for target in settings.probe_targets
    }
    event_publisher = KafkaEventPublisher(settings.kafka_bootstrap_servers)
    ctx = AppContext(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        auditability=HTTPAuditabilityClient(
            settings.auditability_base_url, issuer=settings.service_name, shared_secret=settings.jwt_shared_secret,
        ),
        event_publisher=event_publisher,
        probe_clients=probe_clients,
    )
    return ctx, event_publisher


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: MultiTenancySettings = app.state.settings
    configure_logging(settings.telemetry.log_level)
    configure_tracing(settings.service_name, settings.telemetry.otlp_endpoint)

    if settings.jwt_shared_secret == INSECURE_DEFAULT_SECRET:
        logger.warning(
            "jwt_shared_secret_is_insecure_default",
            hint="set TECTONIC_JWT_SHARED_SECRET in every module sharing this deployment",
        )

    ctx, event_publisher = build_app_context(settings)
    try:
        await event_publisher.start()
    except Exception as exc:
        # See workflow-engine's own main.py (ticket #82) for the full
        # reasoning: an unguarded await here crashed this module's whole
        # process at startup whenever Kafka was unreachable, even though the
        # outbox pattern is fire-and-forget by design and nothing on the
        # synchronous request path needs Kafka. OutboxRelayWorker's own
        # per-event try/except already requeues publish failures for retry
        # without this process going down, so degrading here (log and
        # continue) rather than crashing lets a broker that arrives later
        # drain the backlog with no further code change.
        logger.warning("kafka_event_publisher_start_failed_degraded", error=str(exc))
    app.state.ctx = ctx

    @asynccontextmanager
    async def repository_factory():
        async with ctx.session_factory() as session:
            yield SQLAlchemyMultiTenancyRepository(session)

    outbox_worker = OutboxRelayWorker(
        repository_factory, event_publisher,
        poll_interval_seconds=settings.outbox_worker_poll_interval_seconds,
        lease_seconds=settings.outbox_worker_lease_seconds,
        max_attempts=settings.outbox_worker_max_attempts,
    )
    await outbox_worker.recover_stuck_events()
    outbox_worker_task = asyncio.create_task(outbox_worker.run_forever())
    app.state.outbox_worker = outbox_worker

    logger.info(
        "startup_complete", service=settings.service_name,
        probe_targets=[t.name for t in settings.probe_targets],
        outbox_worker_id=outbox_worker.worker_id,
    )
    try:
        yield
    finally:
        outbox_worker.stop()
        outbox_worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await outbox_worker_task
        await event_publisher.stop()
        await ctx.engine.dispose()
        logger.info("shutdown_complete")


def create_app() -> FastAPI:
    settings = load_settings()

    app = FastAPI(
        title="Multi-tenancy",
        version="0.1.0",
        description="Tectonic Agentic AI Platform — Module 30: tenant registry and lifecycle, "
        "plus a real, executable isolation probe against every platform module's shared tenant-scoped list contract.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        ServiceAuthMiddleware, audience=settings.service_name, shared_secret=settings.jwt_shared_secret,
    )
    app.include_router(multi_tenancy_router)

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
            producer = ctx.event_publisher
            components["kafka"] = "ok" if getattr(producer, "_producer", None) is not None else "degraded: not started"
        except Exception as e:
            components["kafka"] = f"degraded: {e}"

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
