from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from tool_orchestration.config import CircuitBreakerConfig, RetryConfig
from tool_orchestration.core.domain import (
    CircuitOpenError,
    CircuitState,
    ToolCallError,
    ToolDefinitionRecord,
    ToolNotActiveError,
    ToolNotFoundError,
    ToolStatus,
    now,
)

pytestmark = pytest.mark.asyncio


def _tool(**overrides) -> ToolDefinitionRecord:
    defaults = {
        "id": "t1", "tenant_id": "tenant-a", "name": "lookup", "mcp_server_ref": "http://tools/lookup",
    }
    defaults.update(overrides)
    return ToolDefinitionRecord(**defaults)


async def test_successful_invocation_completes_and_updates_reliability(harness):
    harness.repository.seed_tool(_tool())

    outcome = await harness.service.invoke(tool_id="t1", arguments={"q": "hi"}, agent_ref="agent-1", tenant_id="tenant-a")

    assert outcome.status.value == "completed"
    assert outcome.retry_count == 0
    score = await harness.repository.get_reliability_score("t1")
    assert score.rolling_success_rate > 0.8  # EMA nudged up from the default 1.0 by one success, still high
    assert len(harness.repository.invocations) == 1


async def test_tool_not_found_raises(harness):
    with pytest.raises(ToolNotFoundError):
        await harness.service.invoke(tool_id="nope", arguments={}, agent_ref="agent-1", tenant_id="tenant-a")


async def test_inactive_tool_raises(harness):
    harness.repository.seed_tool(_tool(status=ToolStatus.DEPRECATED))
    with pytest.raises(ToolNotActiveError):
        await harness.service.invoke(tool_id="t1", arguments={}, agent_ref="agent-1", tenant_id="tenant-a")


async def test_failure_exhausts_retries_and_raises(harness_factory):
    harness = harness_factory(retry_config=RetryConfig(default_max_retries=1))
    harness.repository.seed_tool(_tool())
    harness.mcp_client.failing_tools.add("lookup")

    with pytest.raises(ToolCallError):
        await harness.service.invoke(tool_id="t1", arguments={}, agent_ref="agent-1", tenant_id="tenant-a")

    invocation = harness.repository.invocations[-1]
    assert invocation.status.value == "failed"
    assert invocation.retry_count == 1


async def test_repeated_failures_trip_circuit_then_reject_calls(harness_factory):
    harness = harness_factory(
        retry_config=RetryConfig(default_max_retries=0),
        circuit_breaker_config=CircuitBreakerConfig(failure_threshold=0.5, open_duration_seconds=60),
    )
    harness.repository.seed_tool(_tool())
    harness.mcp_client.failing_tools.add("lookup")

    # Enough failures to push the EMA success rate below the 0.5 threshold —
    # each of these calls genuinely reaches the tool and fails there, so
    # each still raises ToolCallError (the circuit trips as a side effect
    # of the 4th one, not before it).
    for _ in range(4):
        with pytest.raises(ToolCallError):
            await harness.service.invoke(tool_id="t1", arguments={}, agent_ref="agent-1", tenant_id="tenant-a")

    cb_state = await harness.circuit_breaker_store.get_state("t1")
    assert cb_state.state == CircuitState.OPEN

    # Now the circuit itself rejects the call before ever reaching the tool.
    with pytest.raises(CircuitOpenError):
        await harness.service.invoke(tool_id="t1", arguments={}, agent_ref="agent-1", tenant_id="tenant-a")


async def test_half_open_probe_recovers_circuit(harness_factory):
    harness = harness_factory(
        retry_config=RetryConfig(default_max_retries=0),
        circuit_breaker_config=CircuitBreakerConfig(failure_threshold=0.5, open_duration_seconds=60),
    )
    harness.repository.seed_tool(_tool())
    harness.mcp_client.failing_tools.add("lookup")

    for _ in range(4):  # trips the circuit open, per the EMA math in the sibling test above
        with pytest.raises(ToolCallError):
            await harness.service.invoke(tool_id="t1", arguments={}, agent_ref="agent-1", tenant_id="tenant-a")

    # Fast-forward the retry window instead of sleeping in the test.
    cb_state = await harness.circuit_breaker_store.get_state("t1")
    await harness.circuit_breaker_store.set_state(replace(cb_state, next_retry_at=now() - timedelta(seconds=1)))

    harness.mcp_client.failing_tools.discard("lookup")  # tool has recovered
    outcome = await harness.service.invoke(tool_id="t1", arguments={}, agent_ref="agent-1", tenant_id="tenant-a")

    assert outcome.status.value == "completed"
    cb_state = await harness.circuit_breaker_store.get_state("t1")
    assert cb_state.state == CircuitState.CLOSED
