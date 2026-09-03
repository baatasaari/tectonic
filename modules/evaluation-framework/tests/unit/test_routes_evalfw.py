"""API-level tests for the FastAPI routes -- currently just the ticket
#82 NUL-byte-in-a-raw-string-query-parameter regression on `GET
/scores`. This module wasn't in the sweep's original module list --
found by re-grepping the whole platform for the same pattern once the
sweep was otherwise done: unlike its siblings, its vulnerable
parameters were plain, un-wrapped `str` function parameters rather than
an explicit `Query()` default. No route-level test file existed for
this module before; comprehensive route coverage is a real,
separately-scoped gap (see this module's own README), not one this fix
expands.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from evaluation_framework.api.deps import get_ctx, get_repository
from evaluation_framework.api.routes_evalfw import router
from evaluation_framework.app_context import AppContext
from evaluation_framework.config import EvaluationFrameworkSettings
from evaluation_framework.core.domain import EvalRunRecord, EvalRunStatus, new_id
from evaluation_framework.core.fakes import (
    InMemoryEvaluationFrameworkRepository,
    StubLLMGatewayClient,
)
from evaluation_framework.core.sampler import ProductionSampler
from evaluation_framework.security.jwt_auth import (
    INSECURE_DEFAULT_SECRET,
    ServiceAuthMiddleware,
    mint_service_token,
)

SECRET = INSECURE_DEFAULT_SECRET


def _app(repository):
    app = FastAPI()
    app.add_middleware(ServiceAuthMiddleware, audience="evaluation-framework", shared_secret=SECRET)
    app.include_router(router)

    ctx = AppContext(
        settings=EvaluationFrameworkSettings(), engine=None, session_factory=None,
        llm_gateway=StubLLMGatewayClient(), sampler=ProductionSampler(sample_rate=0.0),
    )
    app.dependency_overrides[get_ctx] = lambda: ctx
    app.dependency_overrides[get_repository] = lambda: repository
    return app


def _token() -> str:
    return mint_service_token(issuer="workflow-engine", audience="evaluation-framework", shared_secret=SECRET)


def _headers():
    return {"Authorization": f"Bearer {_token()}"}


def test_list_scores_rejects_a_null_byte_in_tenant_id_with_a_clean_422():
    """Ticket #82: a raw string query parameter never runs through a
    Pydantic body field's own NUL-byte validator, so this reached the
    repository (and, against real Postgres, the database itself) raw
    instead of a clean 422."""
    app = _app(InMemoryEvaluationFrameworkRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/evaluation-framework/scores", params={"tenant_id": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_list_scores_rejects_a_null_byte_in_agent_ref_with_a_clean_422():
    app = _app(InMemoryEvaluationFrameworkRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/evaluation-framework/scores",
            params={"tenant_id": "acme", "agent_ref": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_list_eval_runs_returns_most_recent_first_scoped_to_agent_ref():
    """The lookup a release-gating caller (PromptOps' `conclude`, LLMOps'
    `promote`) needs to resolve `eval_run_id` before calling `/gate` --
    must exclude another agent_ref's runs and put the newest run first."""
    repo = InMemoryEvaluationFrameworkRepository()
    older = EvalRunRecord(
        id=new_id(), tenant_id="acme", trigger_source="ci_cd", agent_ref="model:x:v1",
        status=EvalRunStatus.COMPLETED,
    )
    newer = EvalRunRecord(
        id=new_id(), tenant_id="acme", trigger_source="ci_cd", agent_ref="model:x:v1",
        status=EvalRunStatus.COMPLETED,
    )
    newer.started_at = older.started_at.replace(year=older.started_at.year + 1)
    other_agent = EvalRunRecord(
        id=new_id(), tenant_id="acme", trigger_source="ci_cd", agent_ref="model:y:v1",
        status=EvalRunStatus.COMPLETED,
    )
    repo.eval_runs = {r.id: r for r in (older, newer, other_agent)}
    app = _app(repo)

    with TestClient(app) as client:
        resp = client.get(
            "/v1/evaluation-framework/eval-runs",
            params={"tenant_id": "acme", "agent_ref": "model:x:v1"}, headers=_headers(),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [newer.id, older.id]


def test_list_eval_runs_rejects_a_null_byte_in_agent_ref_with_a_clean_422():
    app = _app(InMemoryEvaluationFrameworkRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/evaluation-framework/eval-runs",
            params={"tenant_id": "acme", "agent_ref": "a\x00b"}, headers=_headers(),
        )

    assert resp.status_code == 422


def test_evaluate_rejects_a_null_byte_in_a_body_field_with_a_clean_422():
    """This module's own new OpenAPI contract-test tier's very first run
    found this: unlike `GET /scores`'s raw `Query()` string parameters
    (ticket #82), these are Pydantic *body* fields on `EvaluateRequest`
    -- a value `str` is happy to hold, but never ran through any
    NUL-byte validator either, so against real Postgres this reached
    `session.execute()` raw instead of a clean 422 (found on `tenant_id`
    specifically; `agent_ref`/`trigger_source`/`metric_set` items share
    the same `_reject_null_byte` field_validator)."""
    app = _app(InMemoryEvaluationFrameworkRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/evaluation-framework/evaluate",
            json={
                "tenant_id": "a\x00b", "agent_ref": "agent-1", "agent_output": "hello",
                "metric_set": ["faithfulness"],
            },
            headers=_headers(),
        )

    assert resp.status_code == 422


def test_list_eval_runs_rejects_an_offset_beyond_the_bound_with_a_clean_422():
    """The third bug this same contract-test run found: the platform's
    own "unbounded offset" class (CLAUDE.md's own project history --
    already fixed for Billing and Metering's, LLM Gateway's, Multi-
    tenancy's and Workflow Engine's own `offset` query params) recurred
    here too -- an `offset` past Postgres `bigint` range
    (`OFFSET $N::BIGINT`) crashed with an unhandled `asyncpg.DataError`
    instead of a clean 422. Both `GET /eval-runs` and `GET /scores`
    share the same `le=1_000_000_000` bound now; this pins one."""
    app = _app(InMemoryEvaluationFrameworkRepository())

    with TestClient(app) as client:
        resp = client.get(
            "/v1/evaluation-framework/eval-runs",
            params={"tenant_id": "acme", "agent_ref": "agent-1", "offset": 9_223_372_036_854_775_808},
            headers=_headers(),
        )

    assert resp.status_code == 422


def test_create_domain_pack_rejects_a_null_byte_in_a_custom_thresholds_key_with_a_clean_422():
    """A fourth bug this same contract-test run found: `custom_thresholds`
    round-trips as a real `jsonb` column, and jsonb's own text-based
    storage rejects an embedded NUL just like `text`/`varchar` -- whether
    it's a top-level string field or, as here, nested inside a dict
    *key*. Neither the top-level `tenant_id`/`pack_name` validators nor
    ticket #82's original sweep would ever have caught this shape."""
    app = _app(InMemoryEvaluationFrameworkRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/evaluation-framework/domain-packs",
            json={"tenant_id": "acme", "pack_name": "strict", "custom_thresholds": {"a\x00b": 0.9}},
            headers=_headers(),
        )

    assert resp.status_code == 422


def test_gate_returns_a_clean_404_for_a_non_uuid_eval_run_id():
    """The sibling bug this same contract-test run found: `eval_run_id`
    is a Pydantic `str` body field too, but the column it looks up
    (`EvalRun.id`) is a Postgres `UUID` -- `InMemoryEvaluationFrameworkRepository`
    can't reproduce the crash itself (a dict lookup never crashes on a
    malformed key; see this module's own `tests/integration` for the
    real-Postgres regression), but this still pins the route's own
    clean-404 contract for the case the repository fix makes possible."""
    app = _app(InMemoryEvaluationFrameworkRepository())

    with TestClient(app) as client:
        resp = client.post(
            "/v1/evaluation-framework/gate",
            json={"tenant_id": "acme", "eval_run_id": "not-a-uuid"},
            headers=_headers(),
        )

    assert resp.status_code == 404
