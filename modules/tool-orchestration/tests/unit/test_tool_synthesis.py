import pytest

from tool_orchestration.core.domain import SynthesisRejectedError, ToolStatus

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
    assert await harness.repository.list_tool_definitions("tenant-a") == []  # nothing persisted


async def test_require_sentinel_approval_cannot_be_disabled_while_synthesis_enabled():
    from tool_orchestration.config import SynthesisConfig, ToolOrchestrationSettings

    with pytest.raises(ValueError):
        ToolOrchestrationSettings(synthesis=SynthesisConfig(enabled=True, require_sentinel_approval=False))
