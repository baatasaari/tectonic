"""Tests for clients/a2a_peer_client.py -- card fetch, message/send
forwarding, JSON-RPC error surfacing, and the per-peer circuit breaker
isolation this client's docstring claims."""
from __future__ import annotations

import httpx
import pytest
import respx

from a2a_gateway.clients.a2a_peer_client import (
    A2APeerHTTPClient,
    A2APeerRpcError,
    CircuitBreakerError,
)


@respx.mock
async def test_fetch_agent_card_gets_the_well_known_path():
    respx.get("http://peer-a.example/.well-known/agent.json").mock(
        return_value=httpx.Response(200, json={"name": "peer-a", "skills": []})
    )
    client = A2APeerHTTPClient()

    card = await client.fetch_agent_card("http://peer-a.example")

    assert card["name"] == "peer-a"


@respx.mock
async def test_send_message_returns_the_result_object():
    respx.post("http://peer-a.example/v1/a2a/rpc").mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": "x", "result": {"task_id": "t1", "status": "working"}})
    )
    client = A2APeerHTTPClient()

    result = await client.send_message("http://peer-a.example", skill_id="summarize", input_message={"text": "hi"})

    assert result == {"task_id": "t1", "status": "working"}


@respx.mock
async def test_send_message_raises_on_a_jsonrpc_error_response():
    respx.post("http://peer-a.example/v1/a2a/rpc").mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": "x", "error": {"code": -32001, "message": "denied"}})
    )
    client = A2APeerHTTPClient()

    with pytest.raises(A2APeerRpcError) as exc_info:
        await client.send_message("http://peer-a.example", skill_id="summarize", input_message={})

    assert exc_info.value.code == -32001


@respx.mock
async def test_a_struggling_peer_never_trips_a_different_peers_breaker():
    respx.post("http://peer-a.example/v1/a2a/rpc").mock(return_value=httpx.Response(503))
    respx.post("http://peer-b.example/v1/a2a/rpc").mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": "x", "result": {"status": "completed"}})
    )
    client = A2APeerHTTPClient(fail_max=2)

    for _ in range(6):
        with pytest.raises((httpx.HTTPStatusError, CircuitBreakerError)):
            await client.send_message("http://peer-a.example", skill_id="summarize", input_message={})

    # Peer A's breaker is open by now; peer B must be entirely unaffected.
    result = await client.send_message("http://peer-b.example", skill_id="summarize", input_message={})
    assert result == {"status": "completed"}
