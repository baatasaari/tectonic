"""Unit tests for `HTTPDecisionCallbackDispatcher`'s per-call JWT minting
(clients/http_clients.py). Unlike every other HTTP client in this module,
this dispatcher's target audience is only known per-call (`requesting_module`
varies per notify() call), so it can't use the shared construction-time
`ServiceBearerAuth` httpx.Auth flow every other client uses — it mints a
fresh token inline, in `notify()`, scoped to that call's target instead.
"""
from __future__ import annotations

import jwt as pyjwt
import respx
from httpx import Response

from human_oversight.clients.http_clients import HTTPDecisionCallbackDispatcher
from human_oversight.core.domain import DecisionRecord, DecisionType

SECRET = "test-shared-secret-at-least-32-bytes-long"


def _decision() -> DecisionRecord:
    return DecisionRecord(id="d-1", request_id="r-1", decision=DecisionType.APPROVED, decided_by="alice")


@respx.mock
async def test_notify_mints_a_token_scoped_to_the_workflow_engine_audience():
    route = respx.post(
        "http://dep.local/v1/workflow-engine/instances/inst-1/approvals/appr-1/callback",
    ).mock(return_value=Response(200, json={}))

    dispatcher = HTTPDecisionCallbackDispatcher(
        "http://dep.local", issuer="human-oversight", shared_secret=SECRET, ttl_seconds=300,
    )
    await dispatcher.notify("workflow_engine", "inst-1:appr-1", _decision())

    assert route.called
    sent_request = route.calls[0].request
    auth_header = sent_request.headers["authorization"]
    scheme, _, token = auth_header.partition(" ")
    assert scheme == "Bearer"

    claims = pyjwt.decode(token, SECRET, algorithms=["HS256"], audience="workflow-engine")
    assert claims["iss"] == "human-oversight"
    assert claims["aud"] == "workflow-engine"


@respx.mock
async def test_notify_mints_a_token_scoped_to_the_generic_requesting_module_audience():
    route = respx.post("http://dep.local/v1/sentinel_agents/oversight-callback").mock(
        return_value=Response(200, json={}),
    )

    dispatcher = HTTPDecisionCallbackDispatcher(
        "http://dep.local", issuer="human-oversight", shared_secret=SECRET, ttl_seconds=300,
    )
    await dispatcher.notify("sentinel_agents", "alert-1", _decision())

    assert route.called
    sent_request = route.calls[0].request
    auth_header = sent_request.headers["authorization"]
    scheme, _, token = auth_header.partition(" ")
    assert scheme == "Bearer"

    # kebab-cased per this platform's service-name convention
    claims = pyjwt.decode(token, SECRET, algorithms=["HS256"], audience="sentinel-agents")
    assert claims["iss"] == "human-oversight"
    assert claims["aud"] == "sentinel-agents"


@respx.mock
async def test_notify_sends_no_authorization_header_when_no_issuer_configured():
    route = respx.post("http://dep.local/v1/sentinel_agents/oversight-callback").mock(
        return_value=Response(200, json={}),
    )

    dispatcher = HTTPDecisionCallbackDispatcher("http://dep.local")
    await dispatcher.notify("sentinel_agents", "alert-1", _decision())

    assert route.called
    assert "authorization" not in route.calls[0].request.headers
