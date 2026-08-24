import pytest

from tool_orchestration.core.domain import SynthesisRejectedError, ToolDefinitionRecord, ToolStatus

pytestmark = pytest.mark.asyncio


async def test_synthesis_disabled_by_default_rejects(harness):
    with pytest.raises(SynthesisRejectedError):
        await harness.synthesis_engine.synthesise(gap_description="fetch weather", available_primitives=["http_get"], tenant_id="tenant-a")


async def test_enabled_synthesis_creates_pending_review_tool_and_submits_for_sentinel_review(harness_factory):
    from tool_orchestration.config import SynthesisConfig

    harness = harness_factory(synthesis_config=SynthesisConfig(enabled=True, require_sentinel_approval=True))

    tool = await harness.synthesis_engine.synthesise(
        gap_description="fetch weather", available_primitives=["http_get"], tenant_id="tenant-a"
    )

    assert tool.status == ToolStatus.PENDING_REVIEW
    assert tool.synthesised is True
    assert len(harness.sentinel.submissions) == 1
    assert harness.sentinel.submissions[0]["tool_id"] == tool.id

    # Never reaches active on its own — only /tools/{id}/approve does that.
    stored = await harness.repository.get_tool_definition(tool.id)
    assert stored.status == ToolStatus.PENDING_REVIEW


async def test_guardrails_block_prevents_synthesis(harness_factory):
    from tool_orchestration.config import SynthesisConfig

    harness = harness_factory(synthesis_config=SynthesisConfig(enabled=True, require_sentinel_approval=True))
    harness.guardrails.block_next = True

    with pytest.raises(SynthesisRejectedError):
        await harness.synthesis_engine.synthesise(gap_description="fetch weather", available_primitives=[], tenant_id="tenant-a")

    assert harness.sentinel.submissions == []  # never got far enough to request review
    tools, total = await harness.repository.list_tool_definitions("tenant-a")
    assert tools == []  # nothing persisted
    assert total == 0


async def test_require_sentinel_approval_cannot_be_disabled_while_synthesis_enabled():
    from tool_orchestration.config import SynthesisConfig, ToolOrchestrationSettings

    with pytest.raises(ValueError):
        ToolOrchestrationSettings(synthesis=SynthesisConfig(enabled=True, require_sentinel_approval=False))


async def test_list_tool_definitions_paginates_in_created_order(harness):
    from datetime import UTC, datetime, timedelta

    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(3):
        await harness.repository.create_tool_definition(
            ToolDefinitionRecord(
                id=f"tool-{i}", tenant_id="tenant-a", name=f"tool-{i}", mcp_server_ref="srv",
                created_at=base + timedelta(hours=i),
            )
        )

    first_page, total_1 = await harness.repository.list_tool_definitions("tenant-a", limit=2, offset=0)
    second_page, total_2 = await harness.repository.list_tool_definitions("tenant-a", limit=2, offset=2)

    assert total_1 == 3
    assert total_2 == 3
    assert [t.id for t in first_page] == ["tool-0", "tool-1"]  # oldest first, stable order
    assert [t.id for t in second_page] == ["tool-2"]


async def test_list_tool_definitions_empty_result_returns_zero_total(harness):
    tools, total = await harness.repository.list_tool_definitions("no-such-tenant")
    assert tools == []
    assert total == 0
