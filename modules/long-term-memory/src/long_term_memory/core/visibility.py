"""Cross-Agent Visibility Policy (LLD §2 sub-components): determines
which agents can read which memories, reusing Guardrails' policy engine
rather than a separate ACL system. The requesting agent always sees its
own scope; visibility across scopes requires both the tenant's
`cross_agent_sharing.enabled` flag and Guardrails' own approval.
"""
from __future__ import annotations

from long_term_memory.config import CrossAgentSharingConfig
from long_term_memory.core.ports import GuardrailsClient


async def check_visibility(
    scope: str, requesting_agent: str | None, config: CrossAgentSharingConfig, guardrails: GuardrailsClient,
) -> bool:
    if requesting_agent is None or requesting_agent == scope:
        return True
    if not config.enabled:
        return False
    return await guardrails.check_visibility(
        scope=scope, requesting_agent=requesting_agent, policy_ref=config.visibility_policy_ref,
    )
