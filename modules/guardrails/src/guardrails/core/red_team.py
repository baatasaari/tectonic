"""Red-Team Self-Test Job (LLD §2 sub-components, §Level 3 "Sequence:
scheduled red-team self-test detecting drift"): continuously generates
and runs novel adversarial attempts against a shadow policy config,
alerting Sentinel Agents on any bypass.
"""
from __future__ import annotations

from guardrails.core.domain import (
    BypassIncidentRecord,
    CheckStage,
    Decision,
    PolicyProfileRecord,
    RedTeamRunRecord,
    new_id,
)
from guardrails.core.policy_engine import PolicyEngine
from guardrails.core.ports import GuardrailsRepository, LLMGatewayClient, SentinelAgentsClient


class RedTeamRunner:
    def __init__(
        self, repository: GuardrailsRepository, policy_engine: PolicyEngine, llm_gateway: LLMGatewayClient,
        sentinel: SentinelAgentsClient, attempts_per_run: int,
    ) -> None:
        self._repository = repository
        self._policy_engine = policy_engine
        self._llm_gateway = llm_gateway
        self._sentinel = sentinel
        self._attempts_per_run = attempts_per_run

    async def run(self, tenant_id: str, shadow_profile: PolicyProfileRecord) -> RedTeamRunRecord:
        prompts = await self._llm_gateway.generate_adversarial_prompts(self._attempts_per_run, tenant_id)

        bypasses: list[str] = []
        for prompt in prompts:
            result = await self._policy_engine.evaluate(prompt, CheckStage.INPUT, shadow_profile, tenant_id)
            if result.decision != Decision.BLOCK:
                bypasses.append(prompt)

        run = RedTeamRunRecord(
            id=new_id(), tenant_id=tenant_id, attempts_generated=len(prompts), successful_bypasses=len(bypasses),
        )
        run = await self._repository.create_red_team_run(run)

        for prompt in bypasses:
            incident = BypassIncidentRecord(
                id=new_id(), red_team_run_id=run.id, attack_pattern=prompt[:200], target_check="jailbreak_detection",
            )
            await self._repository.create_bypass_incident(incident)

        if bypasses:
            await self._sentinel.alert(
                {"event": "guardrails_bypass", "tenant_id": tenant_id, "run_id": run.id, "count": len(bypasses)}
            )

        return run
