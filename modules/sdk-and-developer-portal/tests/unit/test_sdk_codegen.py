"""Tests for core/sdk_codegen.py -- pure, deterministic, no fake
needed."""
from __future__ import annotations

from sdk_and_developer_portal.core.sdk_codegen import generate_python_client

SPEC = {
    "info": {"title": "Auditability", "version": "0.1.0"},
    "paths": {
        "/v1/auditability/events": {
            "get": {"operationId": "list_events"},
            "post": {"operationId": "ingest_event"},
        },
        "/v1/auditability/events/verify-chain": {
            "get": {"operationId": "verify_chain_route"},
        },
    },
}


def test_generates_a_method_per_path_and_verb():
    source = generate_python_client(module_name="auditability", base_url="http://auditability:8090", spec=SPEC)

    assert "class AuditabilityClient:" in source
    assert "def list_events(self, **kwargs) -> httpx.Response:" in source
    assert "def ingest_event(self, **kwargs) -> httpx.Response:" in source
    assert "def verify_chain_route(self, **kwargs) -> httpx.Response:" in source
    assert "self._client.get('/v1/auditability/events'" in source
    assert "self._client.post('/v1/auditability/events'" in source


def test_is_deterministic_for_the_same_spec():
    a = generate_python_client(module_name="auditability", base_url="http://auditability:8090", spec=SPEC)
    b = generate_python_client(module_name="auditability", base_url="http://auditability:8090", spec=SPEC)

    assert a == b


def test_falls_back_to_method_and_path_when_no_operation_id():
    spec = {"info": {}, "paths": {"/v1/things/{id}": {"get": {}}}}

    source = generate_python_client(module_name="things", base_url="http://things:8000", spec=spec)

    assert "def get_v1_things_id(self, **kwargs) -> httpx.Response:" in source


def test_deduplicates_colliding_operation_ids():
    spec = {
        "info": {},
        "paths": {
            "/a": {"get": {"operationId": "dup"}},
            "/b": {"get": {"operationId": "dup"}},
        },
    }

    source = generate_python_client(module_name="mod", base_url="http://mod", spec=spec)

    assert "def dup(self, **kwargs)" in source
    assert "def dup_2(self, **kwargs)" in source


def test_class_name_derived_from_hyphenated_module_name():
    source = generate_python_client(module_name="secrets-and-credential-management", base_url="http://x", spec=SPEC)

    assert "class SecretsAndCredentialManagementClient:" in source


def test_empty_paths_still_produces_a_valid_client_shell():
    spec = {"info": {"title": "Empty"}, "paths": {}}

    source = generate_python_client(module_name="empty", base_url="http://empty", spec=spec)

    assert "class EmptyClient:" in source
    assert "def __init__(self, base_url: str, token: str) -> None:" in source
