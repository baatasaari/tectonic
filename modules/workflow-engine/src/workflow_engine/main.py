"""FastAPI application entrypoint (LLD §Level 1 stack table, §4.6 Deployment
Specification). `/healthz` verifies Postgres and Kafka connectivity
separately, reporting degraded rather than binary pass/fail, per the LLD.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from workflow_engine.api.routes_definitions import router as definitions_router
from workflow_engine.api.routes_instances import router as instances_router
from workflow_engine.app_context import AppContext
from workflow_engine.clients.http_clients import (
    HTTPGuardrailsClient,
    HTTPHumanOversightClient,
    HTTPLLMGatewayClient,
    HTTPToolOrchestrationClient,
)
from workflow_engine.clients.kafka_publisher import KafkaEventPublisher
from workflow_engine.config import WorkflowEngineSettings, load_settings
from workflow_engine.core.symbolic import SymbolicRuleExecutor
from workflow_engine.db.session import make_engine, make_session_factory
from workflow_engine.security.jwt_auth import INSECURE_DEFAULT_SECRET, ServiceAuthMiddleware
from workflow_engine.telemetry.logging import configure_logging, get_logger
from workflow_engine.telemetry.tracing import configure_tracing

logger = get_logger(component="main")


def build_app_context(settings: WorkflowEngineSettings) -> tuple[AppContext, KafkaEventPublisher]:
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    event_publisher = KafkaEventPublisher(settings.kafka_bootstrap_servers)


    ctx = AppContext(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        event_publisher=event_publisher,
        llm_gateway=HTTPLLMGatewayClient(
            settings.llm_gateway_base_url, issuer=settings.service_name, shared_secret=settings.jwt_shared_secret,
            ttl_seconds=settings.jwt_ttl_seconds,
        ),
        tool_orchestration=HTTPToolOrchestrationClient(
            settings.tool_orchestration_base_url, issuer=settings.service_name, shared_secret=settings.jwt_shared_secret,
            ttl_seconds=settings.jwt_ttl_seconds,
        ),
        guardrails=HTTPGuardrailsClient(
            settings.guardrails_base_url, issuer=settings.service_name, shared_secret=settings.jwt_shared_secret,
            ttl_seconds=settings.jwt_ttl_seconds,
        ),
        human_oversight=HTTPHumanOversightClient(
            settings.human_oversight_base_url, issuer=settings.service_name, shared_secret=settings.jwt_shared_secret,
            ttl_seconds=settings.jwt_ttl_seconds,
        ),
        symbolic_executor=SymbolicRuleExecutor(),
    )
    return ctx, event_publisher


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: WorkflowEngineSettings = app.state.settings
    configure_logging(settings.telemetry.log_level)
    configure_tracing(settings.service_name, settings.telemetry.otlp_endpoint)

    if settings.jwt_shared_secret == INSECURE_DEFAULT_SECRET:
        logger.warning(
            "jwt_shared_secret_is_insecure_default",
            hint="set TECTONIC_JWT_SHARED_SECRET in every module sharing this deployment",
        )

    ctx, event_publisher = build_app_context(settings)
    await event_publisher.start()
    app.state.ctx = ctx

    logger.info("startup_complete", service=settings.service_name, tenant_id=settings.tenant_id)
    try:
        yield
    finally:
        await event_publisher.stop()
        await ctx.engine.dispose()
        logger.info("shutdown_complete")


def create_app() -> FastAPI:
    settings = load_settings()

    app = FastAPI(
        title="Workflow Engine",
        version="0.1.0",
        description="Tectonic Agentic AI Platform — Module 1: executes agent workflows as "
        "DAGs/graphs with neurosymbolic step routing and confidence-gated autonomy.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        ServiceAuthMiddleware, audience=settings.service_name, shared_secret=settings.jwt_shared_secret,
    )
    app.include_router(definitions_router)
    app.include_router(instances_router)

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
        import json

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
