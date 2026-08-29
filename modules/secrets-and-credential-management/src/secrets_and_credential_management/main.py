"""FastAPI application entrypoint (LLD §Level 4 "Deployment")."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from secrets_and_credential_management.api.routes_secrets_and_credential_management import (
    router as secrets_router,
)
from secrets_and_credential_management.app_context import AppContext
from secrets_and_credential_management.clients.auditability_client import HTTPAuditabilityClient
from secrets_and_credential_management.clients.identity_access_client import (
    HTTPIdentityAccessClient,
)
from secrets_and_credential_management.config import (
    SecretsAndCredentialManagementSettings,
    load_settings,
)
from secrets_and_credential_management.core.ports import KeyManagementProvider
from secrets_and_credential_management.db.session import make_engine, make_session_factory
from secrets_and_credential_management.security.envelope_encryption import EnvelopeCipher
from secrets_and_credential_management.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
)
from secrets_and_credential_management.security.key_management import (
    LocalStaticKeyManagementProvider,
    VaultTransitKeyManagementProvider,
)
from secrets_and_credential_management.security.openapi_security import configure_openapi_security
from secrets_and_credential_management.telemetry.logging import configure_logging, get_logger
from secrets_and_credential_management.telemetry.tracing import configure_tracing

logger = get_logger(component="main")

INSECURE_DEFAULT_MASTER_KEY = "TjDlTNIHnInVxA0zsGHYi6iTjBRtCSnWVcGxrYLXaYc="


def build_key_management_provider(settings: SecretsAndCredentialManagementSettings) -> KeyManagementProvider:
    if settings.kms_provider == "vault":
        return VaultTransitKeyManagementProvider(
            settings.vault_addr, vault_token=settings.vault_token, key_name=settings.vault_transit_key_name,
        )
    return LocalStaticKeyManagementProvider(master_key=settings.secrets_master_key)


def build_app_context(settings: SecretsAndCredentialManagementSettings) -> AppContext:
    engine = make_engine(settings)
    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        identity_access=HTTPIdentityAccessClient(
            settings.identity_access_base_url, issuer=settings.service_name,
            shared_secret=settings.jwt_shared_secret,
        ),
        auditability=HTTPAuditabilityClient(
            settings.auditability_base_url, issuer=settings.service_name, shared_secret=settings.jwt_shared_secret,
        ),
        cipher=EnvelopeCipher(key_provider=build_key_management_provider(settings)),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: SecretsAndCredentialManagementSettings = app.state.settings
    configure_logging(settings.telemetry.log_level)
    configure_tracing(settings.service_name, settings.telemetry.otlp_endpoint)

    if settings.jwt_shared_secret == INSECURE_DEFAULT_SECRET:
        logger.warning(
            "jwt_shared_secret_is_insecure_default",
            hint="set TECTONIC_JWT_SHARED_SECRET in every module sharing this deployment",
        )
    if settings.kms_provider == "local":
        logger.warning(
            "kms_provider_is_local_not_a_managed_kms",
            hint="set SECRETS_KMS_PROVIDER=vault (and VAULT_TOKEN/SECRETS_VAULT_ADDR) for a real "
            "managed-KMS-backed root key in production -- see security/key_management.py",
        )
        if settings.secrets_master_key == INSECURE_DEFAULT_MASTER_KEY:
            logger.warning(
                "secrets_master_key_is_insecure_default",
                hint="set SECRETS_MASTER_KEY before storing real secret values with the local provider",
            )

    ctx = build_app_context(settings)
    app.state.ctx = ctx

    logger.info("startup_complete", service=settings.service_name)
    try:
        yield
    finally:
        await ctx.engine.dispose()
        logger.info("shutdown_complete")


def create_app() -> FastAPI:
    settings = load_settings()

    app = FastAPI(
        title="Secrets and Credential Management",
        version="0.1.0",
        description="Tectonic Agentic AI Platform — Module 32: a per-tenant secret vault, encrypted at rest, "
        "retrieved only through a real zero-trust authorization gate, with tracked rotation compliance.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        ServiceAuthMiddleware, audience=settings.service_name, shared_secret=settings.jwt_shared_secret,
    )
    app.include_router(secrets_router)

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
