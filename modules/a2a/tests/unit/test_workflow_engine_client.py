"""Tests for clients/workflow_engine_client.py -- a fixed-base_url
ResilientHTTPClient, unlike the peer client."""
from __future__ import annotations

import httpx
import respx

from a2a_gateway.clients.workflow_engine_client import WorkflowEngineHTTPClient


@respx.mock
async def test_start_instance_posts_to_the_instances_endpoint_with_tenant_header():
    route = respx.post("http://workflow-engine.local/v1/workflow-engine/instances").mock(
        return_value=httpx.Response(201, json={"id": "wf-1", "status": "running", "trace_id": "t1"})
    )
    client = WorkflowEngineHTTPClient("http://workflow-engine.local")

    result = await client.start_instance(definition_id="def-1", tenant_id="acme", initial_context={"a": 1})

    assert result == {"id": "wf-1", "status": "running", "trace_id": "t1"}
    sent = route.calls.last.request
    assert sent.headers["X-Tenant-Id"] == "acme"
