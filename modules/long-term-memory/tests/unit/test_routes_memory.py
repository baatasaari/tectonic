"""API-level tests for the FastAPI routes -- currently just the ticket
#82 NUL-byte-in-a-raw-string-query-parameter regression on `GET
/reflections`. This module wasn't in the sweep's original module list
-- found by re-grepping the whole platform for the same pattern once
the sweep was otherwise done: `agent_ref` there is a plain, un-wrapped
`str` function parameter rather than an explicit `Query()` default. No
route-level test file existed for this module before; comprehensive
route coverage is a real, separately-scoped gap (see this module's own
README), not one this fix expands.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from long_term_memory.api.deps import get_ctx, get_repository
from long_term_memory.api.routes_memory import router
from long_term_memory.app_context import AppContext
from long_term_memory.config import LongTermMemorySettings
from long_term_memory.core.fakes import (
    InMemoryLongTermMemoryRepository,
    StubGraphDBClient,
    StubGuardrailsClient,
    StubLLMGatewayClient,
    StubVectorDBClient,
)
from long_term_memory.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="long-term-memory", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=LongTermMemorySettings(), engine=None, session_factory=None,
        vector_db=StubVectorDBClient(), graph_db=StubGraphDBClient(),
        llm_gateway=StubLLMGatewayClient(), guardrails=StubGuardrailsClient(),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="evaluation-framework", audience="long-term-memory", shared_secret=SECRET)


def _headers():
    return {"Authorization": f"Bearer {_token()}"}


def test_list_reflections_rejects_a_null_byte_in_agent_ref_with_a_clean_422():
    """Ticket #82: a raw string query parameter never runs through a
    Pydantic body field's own NUL-byte validator, so this reached the
    repository (and, against real Postgres, the database itself) raw
    instead of a clean 422."""
    app = _app(InMemoryLongTermMemoryRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/long-term-memory/reflections", params={"agent_ref": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


# Memory governance routes: consent-records, legal-holds, and the erasure
# request's own interaction with an active hold.


def test_grant_and_revoke_consent_end_to_end():
    app = _app(InMemoryLongTermMemoryRepository())
    headers = _headers()

    with TestClient(app) as client:
        granted = client.post(
            "/v1/long-term-memory/consent-records",
            json={"scope": "user:alice", "purpose": "personalization", "basis": "explicit", "granted_by": "alice"},
            headers=headers,
        )
        assert granted.status_code == 201
        consent = granted.json()
        assert consent["revoked_at"] is None

        listed = client.get(
            "/v1/long-term-memory/consent-records", params={"scope": "user:alice"}, headers=headers,
        ).json()
        assert listed["items"][0]["id"] == consent["id"]

        revoked = client.post(
            f"/v1/long-term-memory/consent-records/{consent['id']}/revoke", headers=headers,
        )
        assert revoked.status_code == 200
        assert revoked.json()["revoked_at"] is not None


def test_granting_consent_with_an_invalid_basis_returns_a_clean_422():
    """`basis` is typed as the real ConsentBasis enum, not a bare `str`
    hand-converted at the route -- an invalid value must get a clean 422,
    not an unhandled 500."""
    app = _app(InMemoryLongTermMemoryRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/long-term-memory/consent-records",
            json={"scope": "user:alice", "purpose": "personalization", "basis": "not-a-real-basis"},
            headers=_headers(),
        )

    assert resp.status_code == 422


def test_revoking_an_unknown_consent_id_returns_404():
    app = _app(InMemoryLongTermMemoryRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/long-term-memory/consent-records/does-not-exist/revoke", headers=_headers(),
        )

    assert resp.status_code == 404


def test_place_and_release_legal_hold_end_to_end():
    app = _app(InMemoryLongTermMemoryRepository())
    headers = _headers()

    with TestClient(app) as client:
        placed = client.post(
            "/v1/long-term-memory/legal-holds",
            json={"scope": "user:alice", "reason": "active litigation", "placed_by": "legal-team"},
            headers=headers,
        )
        assert placed.status_code == 201
        hold = placed.json()
        assert hold["released_at"] is None

        listed = client.get(
            "/v1/long-term-memory/legal-holds", params={"scope": "user:alice"}, headers=headers,
        ).json()
        assert listed["items"][0]["id"] == hold["id"]

        released = client.post(
            f"/v1/long-term-memory/legal-holds/{hold['id']}/release", headers=headers,
        )
        assert released.status_code == 200
        assert released.json()["released_at"] is not None


def test_releasing_an_unknown_hold_id_returns_404():
    app = _app(InMemoryLongTermMemoryRepository())

    with TestClient(app) as client:
        resp = client.post("/v1/long-term-memory/legal-holds/does-not-exist/release", headers=_headers())

    assert resp.status_code == 404


def test_erasure_request_for_a_scope_under_legal_hold_returns_409():
    app = _app(InMemoryLongTermMemoryRepository())
    headers = _headers()

    with TestClient(app) as client:
        client.post(
            "/v1/long-term-memory/items",
            json={"scope": "user:alice", "memory_type": "fact", "content": "a fact"}, headers=headers,
        )
        client.post(
            "/v1/long-term-memory/legal-holds",
            json={"scope": "user:alice", "reason": "active litigation"}, headers=headers,
        )

        resp = client.post(
            "/v1/long-term-memory/erasure-requests",
            json={"subject_ref": "user:alice", "requested_by": "compliance-officer"}, headers=headers,
        )

    assert resp.status_code == 409


def test_store_item_rejects_a_null_byte_in_purpose_with_a_clean_422():
    app = _app(InMemoryLongTermMemoryRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/long-term-memory/items",
            json={"scope": "user:alice", "memory_type": "fact", "content": "a fact", "purpose": "a\x00b"},
            headers=_headers(),
        )

    assert resp.status_code == 422


def test_list_consent_records_rejects_a_null_byte_in_scope_with_a_clean_422():
    app = _app(InMemoryLongTermMemoryRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/long-term-memory/consent-records", params={"scope": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_list_legal_holds_rejects_a_null_byte_in_scope_with_a_clean_422():
    app = _app(InMemoryLongTermMemoryRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/long-term-memory/legal-holds", params={"scope": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422
