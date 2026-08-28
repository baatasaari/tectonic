"""Tests for security/openapi_security.py -- the real securitySchemes
declaration this module's generated OpenAPI document previously lacked
entirely (independent architecture assessment §3.6).
"""
from __future__ import annotations

from promptops.main import app
from promptops.security.jwt_auth import _EXCLUDED_PATHS


def test_the_security_scheme_is_declared():
    schema = app.openapi()

    scheme = schema["components"]["securitySchemes"]["ServiceBearerAuth"]
    assert scheme["type"] == "http"
    assert scheme["scheme"] == "bearer"
    assert scheme["bearerFormat"] == "JWT"


def test_the_global_default_requires_the_bearer_scheme():
    schema = app.openapi()

    assert schema["security"] == [{"ServiceBearerAuth": []}]


def test_every_path_this_middleware_actually_excludes_is_explicitly_unauthenticated():
    schema = app.openapi()

    for path in _EXCLUDED_PATHS:
        for operation in schema["paths"][path].values():
            assert operation["security"] == []


def test_a_regular_operation_inherits_the_global_default_rather_than_overriding_it():
    schema = app.openapi()

    # No per-operation "security" key at all -- per the OpenAPI spec, that means "use the
    # document-level default", which the two tests above already prove requires auth. An
    # explicit empty list here would be wrong: it would mean "this operation is
    # unauthenticated", the opposite of reality. Any path this module actually serves
    # beyond its own _EXCLUDED_PATHS proves the point -- no need to name one specifically.
    non_excluded_paths = {p: ops for p, ops in schema["paths"].items() if p not in _EXCLUDED_PATHS}
    assert non_excluded_paths, "this module has no non-excluded paths to check"
    for operations in non_excluded_paths.values():
        for method, operation in operations.items():
            if method in ("get", "post", "put", "patch", "delete", "head", "options"):
                assert "security" not in operation


def test_the_schema_is_cached_after_the_first_call():
    app.openapi_schema = None
    first = app.openapi()
    assert app.openapi() is first
