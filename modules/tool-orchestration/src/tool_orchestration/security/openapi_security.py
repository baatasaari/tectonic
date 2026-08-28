"""Declares this module's real inbound authentication scheme in its own
OpenAPI document (independent architecture assessment §3.6: "Every
OpenAPI document must include OAuth/OIDC security schemes"). FastAPI's
automatic OpenAPI generation has no visibility into
`ServiceAuthMiddleware` (`security/jwt_auth.py`) at all -- it's plain
Starlette middleware, not a FastAPI `Security()`/`Depends()`
dependency, so every module's generated spec previously declared zero
`securitySchemes` and zero per-operation `security` requirements, even
though every request (`/healthz`/`/metrics` excepted) genuinely does
require one. This makes the spec match what the middleware actually
enforces, so a client generated from it, or a contract test run against
it, gets the auth requirement right without reading this module's
source.

Reuses `jwt_auth.py`'s own `_EXCLUDED_PATHS` rather than a second,
separately-maintained list here -- one source of truth per module for
"which paths skip auth", so a module with a non-default exclusion set
(A2A adds its own two well-known unauthenticated paths) is handled
correctly with no special-casing in this file.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from tool_orchestration.security.jwt_auth import _EXCLUDED_PATHS

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})

_SECURITY_SCHEME_NAME = "ServiceBearerAuth"
_SECURITY_SCHEME = {
    "type": "http",
    "scheme": "bearer",
    "bearerFormat": "JWT",
    "description": (
        "Service-to-service HS256 JWT bearer auth (security/jwt_auth.py): every "
        "inbound request must carry `Authorization: Bearer <token>`, verified against "
        "this module's own service_name as the required audience (TECTONIC_JWT_SHARED_SECRET, "
        "one shared signing key across every module in this deployment). Not a user-facing "
        "OAuth/OIDC flow -- see this module's README for the full design note."
    ),
}


def configure_openapi_security(app: FastAPI) -> None:
    """Call once from create_app(), after every route is registered."""

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
        schema.setdefault("components", {}).setdefault("securitySchemes", {})[_SECURITY_SCHEME_NAME] = (
            _SECURITY_SCHEME
        )
        schema["security"] = [{_SECURITY_SCHEME_NAME: []}]

        for path, operations in schema.get("paths", {}).items():
            if path not in _EXCLUDED_PATHS:
                continue
            for method, operation in operations.items():
                if method in _HTTP_METHODS and isinstance(operation, dict):
                    operation["security"] = []

        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi
