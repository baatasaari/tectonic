import pytest

from tool_orchestration.config import RetryConfig
from tool_orchestration.core.domain import ToolCallError, ToolDefinitionRecord
from tool_orchestration.core.fakes import FakeMCPClientAdapter
from tool_orchestration.core.retry_manager import RetryManager

pytestmark = pytest.mark.asyncio


async def _noop_sleep(_seconds: float) -> None:
    return None


def _tool(**schema_overrides) -> ToolDefinitionRecord:
    return ToolDefinitionRecord(
        id="t1", tenant_id="tenant-a", name="lookup", mcp_server_ref="http://tools/lookup",
        schema={"retry_policy": schema_overrides} if schema_overrides else {},
    )


async def test_succeeds_first_try_no_retries():
    client = FakeMCPClientAdapter()
    manager = RetryManager(client, RetryConfig(), sleep_fn=_noop_sleep, backoff_base_seconds=0.0)

    outcome = await manager.call_with_retry(_tool(), {}, "agent-1", "tenant-a")

    assert outcome.success is True
    assert outcome.retry_count == 0


class _FlakyThenSucceedsClient:
    """Fails its first `fail_count` calls, then succeeds — for testing that
    retry actually recovers rather than just exhausting."""

    def __init__(self, fail_count: int) -> None:
        self.fail_count = fail_count
        self.calls = 0

    async def call(self, *, mcp_server_ref, tool_name, arguments, tenant_id):
        self.calls += 1
        if self.calls <= self.fail_count:
            raise ToolCallError(tool_name, "flaky")
        return {"ok": True}


async def test_retries_up_to_configured_max_then_succeeds():
    client = _FlakyThenSucceedsClient(fail_count=2)
    manager = RetryManager(client, RetryConfig(default_max_retries=3), sleep_fn=_noop_sleep, backoff_base_seconds=0.0)

    outcome = await manager.call_with_retry(_tool(), {}, "agent-1", "tenant-a")

    assert outcome.success is True
    assert outcome.retry_count == 2
    assert client.calls == 3


async def test_exhausts_retries_and_fails():
    client = FakeMCPClientAdapter()
    client.failing_tools.add("lookup")
    manager = RetryManager(client, RetryConfig(default_max_retries=2), sleep_fn=_noop_sleep, backoff_base_seconds=0.0)

    outcome = await manager.call_with_retry(_tool(), {}, "agent-1", "tenant-a")

    assert outcome.success is False
    assert outcome.retry_count == 2
    assert outcome.error is not None


async def test_per_tool_retry_policy_overrides_default():
    client = FakeMCPClientAdapter()
    client.failing_tools.add("lookup")
    manager = RetryManager(client, RetryConfig(default_max_retries=5), sleep_fn=_noop_sleep, backoff_base_seconds=0.0)

    outcome = await manager.call_with_retry(_tool(max_retries=0), {}, "agent-1", "tenant-a")

    assert outcome.retry_count == 0  # tool-level override wins over the higher platform default
