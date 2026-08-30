"""Drift Detection Service (LLD §2 sub-components): reuses the exact
same two-proportion z-test the A/B Testing Service uses at launch, here
comparing an active version's pass rate *right now* against its pass
rate *at the moment it was promoted* -- a real, computed "drift
incident" (the LLD's own key metric), not a vague warning nobody can
act on.
"""
from __future__ import annotations

from promptops.core.ab_testing_service import evaluation_ref
from promptops.core.domain import DriftCheckResult, PromptVersionNotFoundError, PromptVersionRecord
from promptops.core.ports import EvaluationFrameworkClient, PromptOpsRepository
from promptops.core.statistics import two_proportion_z_test


class DriftDetectionService:
    def __init__(
        self, repository: PromptOpsRepository, evaluation_framework: EvaluationFrameworkClient, *,
        significance_level: float = 0.05,
    ) -> None:
        self._repository = repository
        self._evaluation_framework = evaluation_framework
        self._significance_level = significance_level

    async def check(self, prompt_version_id: str) -> DriftCheckResult:
        version: PromptVersionRecord | None = await self._repository.get_prompt_version(prompt_version_id)
        if version is None:
            raise PromptVersionNotFoundError(prompt_version_id)

        if version.promoted_pass_rate is None or version.promoted_sample_size is None:
            return DriftCheckResult(
                baseline_pass_rate=None, current_pass_rate=None, current_sample_size=0, p_value=None,
                drifted=False, reason="no baseline: this version was never promoted through an A/B test",
            )

        current_scores = await self._evaluation_framework.list_scores(
            tenant_id=version.tenant_id, agent_ref=evaluation_ref(version.prompt_name, version.version),
        )
        current_n = len(current_scores)
        if current_n == 0:
            return DriftCheckResult(
                baseline_pass_rate=version.promoted_pass_rate, current_pass_rate=None, current_sample_size=0,
                p_value=None, drifted=False, reason="insufficient_data: no current evaluation history",
            )

        current_passed = sum(1 for s in current_scores if s.get("passed"))
        current_pass_rate = current_passed / current_n

        baseline_passed = round(version.promoted_pass_rate * version.promoted_sample_size)
        _, p_value = two_proportion_z_test(
            baseline_passed, version.promoted_sample_size, current_passed, current_n,
        )

        # Only a *drop* counts as drift -- an improvement over the baseline is never an
        # incident, even if it happens to be statistically significant.
        drifted = p_value < self._significance_level and current_pass_rate < version.promoted_pass_rate
        reason = (
            f"drifted: current pass rate {current_pass_rate:.2%} significantly below "
            f"baseline {version.promoted_pass_rate:.2%} (p={p_value:.4f})" if drifted
            else f"no drift: p={p_value:.4f}"
        )
        return DriftCheckResult(
            baseline_pass_rate=version.promoted_pass_rate, current_pass_rate=current_pass_rate,
            current_sample_size=current_n, p_value=p_value, drifted=drifted, reason=reason,
        )
