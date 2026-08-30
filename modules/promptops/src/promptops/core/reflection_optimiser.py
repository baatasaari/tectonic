"""Reflection Optimiser (LLD §2 sub-components): the one bounded
autonomous action this module takes -- given a struggling version's
real failing-metric summary from Evaluation Framework, asks LLM Gateway
to draft an improved template, and returns it as a brand-new `draft`
version. It never overwrites the original, never starts an A/B test
itself, and never promotes anything -- a human or CI pipeline still has
to explicitly `start` an A/B test against it, the same "one bounded
action, everything else stays manual" shape FinOps' own Cost
Optimisation Agent already established for autonomous-agent safety.
"""
from __future__ import annotations

from promptops.core.ab_testing_service import evaluation_ref
from promptops.core.domain import PromptVersionNotFoundError, PromptVersionRecord, new_id
from promptops.core.ports import EvaluationFrameworkClient, LLMGatewayClient, PromptOpsRepository

_REFLECTION_PROMPT_TEMPLATE = """You are improving a prompt template that is underperforming in production.

Current template:
---
{template}
---

It is failing these evaluation metrics (score vs. required threshold):
{failing_metrics}

Propose an improved version of the template that addresses these failures. \
Return ONLY the improved template text, with no explanation or preamble."""


def _format_failing_metrics(scores: list[dict]) -> str:
    failing = [s for s in scores if not s.get("passed")]
    if not failing:
        return "(none in the current sample)"
    lines = [f"- {s.get('metric_name')}: {s.get('score'):.2f} (threshold {s.get('threshold'):.2f})" for s in failing]
    return "\n".join(lines)


class ReflectionOptimiser:
    def __init__(
        self, repository: PromptOpsRepository, evaluation_framework: EvaluationFrameworkClient,
        llm_gateway: LLMGatewayClient, *,
        max_pass_rate_before_reflection: float = 0.9, min_reflection_sample_size: int = 10,
        reflection_model: str = "gpt-4o-mini",
    ) -> None:
        self._repository = repository
        self._evaluation_framework = evaluation_framework
        self._llm_gateway = llm_gateway
        self._max_pass_rate_before_reflection = max_pass_rate_before_reflection
        self._min_reflection_sample_size = min_reflection_sample_size
        self._reflection_model = reflection_model

    async def propose(self, prompt_version_id: str) -> PromptVersionRecord | None:
        version = await self._repository.get_prompt_version(prompt_version_id)
        if version is None:
            raise PromptVersionNotFoundError(prompt_version_id)

        scores = await self._evaluation_framework.list_scores(
            tenant_id=version.tenant_id, agent_ref=evaluation_ref(version.prompt_name, version.version),
        )
        sample_size = len(scores)
        if sample_size < self._min_reflection_sample_size:
            return None  # not enough evidence yet to know whether this version needs help

        pass_rate = sum(1 for s in scores if s.get("passed")) / sample_size
        if pass_rate >= self._max_pass_rate_before_reflection:
            return None  # already performing well -- nothing to optimise away from

        reflection_prompt = _REFLECTION_PROMPT_TEMPLATE.format(
            template=version.template, failing_metrics=_format_failing_metrics(scores),
        )
        improved_template = await self._llm_gateway.generate(
            tenant_id=version.tenant_id, model=self._reflection_model, prompt=reflection_prompt,
        )

        new_version = PromptVersionRecord(
            id=new_id(), tenant_id=version.tenant_id, prompt_name=version.prompt_name,
            version=f"{version.version}-reflect-{new_id()[:8]}", template=improved_template.strip(),
            parent_version_id=version.id,
        )
        return await self._repository.create_prompt_version(new_version)
