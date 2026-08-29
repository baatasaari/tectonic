"""FastAPI application entrypoint (LLD §Level 4 "Deployment")."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from identity_and_access.api.routes_identity_and_access import router as identity_and_access_router
from identity_and_access.api.routes_scim import router as scim_router
from identity_and_access.app_context import AppContext
from identity_and_access.clients.auditability_client import HTTPAuditabilityClient
from identity_and_access.config import IdentityAndAccessSettings, load_settings
from identity_and_access.db.session import make_engine, make_session_factory
from identity_and_access.security.jwt_auth import INSECURE_DEFAULT_SECRET, ServiceAuthMiddleware
from identity_and_access.security.oidc_verifier import HTTPOidcTokenVerifier
from identity_and_access.security.openapi_security import configure_openapi_security
from identity_and_access.security.saml_verifier import XmlDsigSamlAssertionVerifier
from identity_and_access.security.token_signer import JWTTokenSigner
from identity_and_access.telemetry.logging import configure_logging, get_logger
from identity_and_access.telemetry.tracing import configure_tracing

logger = get_logger(component="main")

INSECURE_DEFAULT_TOKEN_SIGNING_SECRET = "dev-insecure-token-signing-secret-change-me"


def build_app_context(settings: IdentityAndAccessSettings) -> AppContext:
    engine = make_engine(settings)
    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        auditability=HTTPAuditabilityClient(
            settings.auditability_base_url, issuer=settings.service_name, shared_secret=settings.jwt_shared_secret,
        ),
        signer=JWTTokenSigner(signing_secret=settings.token_signing_secret),
        # No ServiceBearerAuth here, deliberately: the peer is an arbitrary external
        # IdP's JWKS endpoint, not a platform module -- it holds neither
        # TECTONIC_JWT_SHARED_SECRET nor any reason to expect it.
        oidc_verifier=HTTPOidcTokenVerifier(client=httpx.AsyncClient(timeout=httpx.Timeout(10.0))),
        # No network client needed: unlike OIDC's JWKS fetch, everything a SAML
        # assertion's signature is verified against (the IdP's x509_certificate) is
        # already stored on the IdentityProviderRecord itself.
        saml_verifier=XmlDsigSamlAssertionVerifier(),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: IdentityAndAccessSettings = app.state.settings
    configure_logging(settings.telemetry.log_level)
    configure_tracing(settings.service_name, settings.telemetry.otlp_endpoint)

    if settings.jwt_shared_secret == INSECURE_DEFAULT_SECRET:
        logger.warning(
            "jwt_shared_secret_is_insecure_default",
            hint="set TECTONIC_JWT_SHARED_SECRET in every module sharing this deployment",
        )
    if settings.token_signing_secret == INSECURE_DEFAULT_TOKEN_SIGNING_SECRET:
        logger.warning(
            "token_signing_secret_is_insecure_default",
            hint="set IDENTITY_ACCESS_TOKEN_SIGNING_SECRET before issuing tokens in production",
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
        title="Identity and Access",
        version="0.1.0",
        description="Tectonic Agentic AI Platform — Module 31: zero-trust identity registry, "
        "role/scope-based tokens, and a live authorize gate whose revocation checks take effect immediately.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        ServiceAuthMiddleware, audience=settings.service_name, shared_secret=settings.jwt_shared_secret,
    )
    app.include_router(identity_and_access_router)
    app.include_router(scim_router)

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
