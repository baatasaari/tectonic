"""NeMo Guardrails Policy Engine (LLD §2 sub-components) — deviation from
NVIDIA NeMo Guardrails; see the module README's "Design notes vs. the
LLD". Orchestrates which checks run, in what order, per policy profile
(LLD §Level 3 sequences: "input check blocking a jailbreak attempt",
"output check with PII redaction").

**`context` parameter.** The LLD's `/check` request shape
(`text, stage, policy_profile_id`) doesn't carry a field for the context
an output should be grounded against — a necessary omission to fix,
since groundedness checking is meaningless without it. `context` is
accepted as an optional field alongside the LLD's documented ones.
"""
from __future__ import annotations

from guardrails.core import groundedness_checker, jailbreak_detector, pii_detector
from guardrails.core.domain import CheckResult, CheckStage, Decision, PolicyProfileRecord
from guardrails.core.jailbreak_detector import DetectionResult
from guardrails.core.ports import LLMGatewayClient


class PolicyEngine:
    def __init__(self, llm_gateway: LLMGatewayClient) -> None:
        self._llm_gateway = llm_gateway

    async def evaluate(
        self, text: str, stage: CheckStage, profile: PolicyProfileRecord, tenant_id: str, context: str | None = None,
    ) -> CheckResult:
        checks_run: list[str] = []

        if stage == CheckStage.INPUT and "jailbreak_detection" in profile.enabled_checks:
            checks_run.append("jailbreak_detection")
            result = jailbreak_detector.detect(text)
            if result == DetectionResult.DETECTED:
                return CheckResult(Decision.BLOCK, "jailbreak", None, checks_run)
            if result == DetectionResult.AMBIGUOUS:
                classification = await self._llm_gateway.classify_intent(text, tenant_id)
                if classification == "jailbreak_attempt":
                    return CheckResult(Decision.BLOCK, "jailbreak", None, checks_run)

        if profile.denied_topics:
            checks_run.append("denied_topics")
            lowered = text.lower()
            if any(topic.lower() in lowered for topic in profile.denied_topics):
                return CheckResult(Decision.BLOCK, "denied_topic", None, checks_run)

        if stage == CheckStage.OUTPUT and "groundedness_check" in profile.enabled_checks and context is not None:
            checks_run.append("groundedness_check")
            if not groundedness_checker.is_grounded(text, context, profile.groundedness_threshold):
                return CheckResult(Decision.BLOCK, "ungrounded", None, checks_run)

        if "pii_detection" in profile.enabled_checks:
            checks_run.append("pii_detection")
            redacted, entities = pii_detector.detect_and_redact(text, profile.pii_entity_types)
            if entities:
                return CheckResult(Decision.REDACT, "pii", redacted, checks_run)

        return CheckResult(Decision.ALLOW, None, None, checks_run)
