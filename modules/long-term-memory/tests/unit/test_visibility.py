from long_term_memory.config import CrossAgentSharingConfig
from long_term_memory.core.fakes import StubGuardrailsClient
from long_term_memory.core.visibility import check_visibility


async def test_owner_always_allowed():
    guardrails = StubGuardrailsClient()
    allowed = await check_visibility("agent:a", "agent:a", CrossAgentSharingConfig(enabled=False), guardrails)
    assert allowed is True
    assert guardrails.calls == []


async def test_no_requesting_agent_always_allowed():
    guardrails = StubGuardrailsClient()
    allowed = await check_visibility("agent:a", None, CrossAgentSharingConfig(enabled=False), guardrails)
    assert allowed is True


async def test_cross_agent_denied_when_sharing_disabled():
    guardrails = StubGuardrailsClient()
    allowed = await check_visibility("agent:a", "agent:b", CrossAgentSharingConfig(enabled=False), guardrails)
    assert allowed is False
    assert guardrails.calls == []


async def test_cross_agent_delegates_to_guardrails_when_sharing_enabled():
    guardrails = StubGuardrailsClient()
    guardrails.allow = True
    allowed = await check_visibility(
        "agent:a", "agent:b", CrossAgentSharingConfig(enabled=True, visibility_policy_ref="p1"), guardrails,
    )
    assert allowed is True
    assert guardrails.calls[0] == {"scope": "agent:a", "requesting_agent": "agent:b", "policy_ref": "p1"}


async def test_cross_agent_denied_when_guardrails_rejects():
    guardrails = StubGuardrailsClient()
    guardrails.allow = False
    allowed = await check_visibility("agent:a", "agent:b", CrossAgentSharingConfig(enabled=True), guardrails)
    assert allowed is False
