"""A/B Testing Service (LLD §2 sub-components, §Level 3 "A/B
significance test"): a real two-proportion z-test between two prompt
versions' Evaluation Framework score histories. `evaluate` never picks
a winner on a sample too small to mean anything; `conclude` always
re-runs it fresh -- it never trusts an earlier verdict. `conclude` also
blocks promotion on Evaluation Framework's own `POST /gate` verdict for
the winner's most recent eval run -- the evaluation-gated release path
(this module's own "publish" moment; a winner failing its own most
recent evaluation is a real, separately-scoped failure mode from "not
enough A/B signal yet").
"""
from __future__ import annotations

from promptops.core.domain import (
    ABTestNotConclusiveError,
    ABTestNotFoundError,
    ABTestRecord,
    ABTestResult,
    ABTestStatus,
    EvaluationGateFailedError,
    InvalidTransitionError,
    PromptVersionNotFoundError,
    PromptVersionRecord,
    PromptVersionStatus,
    is_legal_transition,
    new_id,
    now,
)
from promptops.core.ports import EvaluationFrameworkClient, PromptOpsRepository
from promptops.core.statistics import two_proportion_z_test


def evaluation_ref(prompt_name: str, version: str) -> str:
    """The `agent_ref` a prompt version's own evaluation runs must be
    tagged with for this service to find them -- the same dedicated-
    attribution-convention shape LLMOps' `evaluation_ref` and
    Deployment Strategy's `deployment_ref` already established."""
    return f"prompt:{prompt_name}:{version}"


class ABTestingService:
    def __init__(
        self, repository: PromptOpsRepository, evaluation_framework: EvaluationFrameworkClient, *,
        min_sample_size_per_arm: int = 10, significance_level: float = 0.05,
    ) -> None:
        self._repository = repository
        self._evaluation_framework = evaluation_framework
        self._min_sample_size_per_arm = min_sample_size_per_arm
        self._significance_level = significance_level

    async def _get_version(self, version_id: str) -> PromptVersionRecord:
        record = await self._repository.get_prompt_version(version_id)
        if record is None:
            raise PromptVersionNotFoundError(version_id)
        return record

    async def start(self, *, tenant_id: str, prompt_name: str, version_a_id: str, version_b_id: str) -> ABTestRecord:
        version_a = await self._get_version(version_a_id)
        version_b = await self._get_version(version_b_id)

        for version in (version_a, version_b):
            if not is_legal_transition(version.status, PromptVersionStatus.TESTING):
                raise InvalidTransitionError(version.status, PromptVersionStatus.TESTING)

        version_a.status = PromptVersionStatus.TESTING
        version_a.updated_at = now()
        await self._repository.update_prompt_version(version_a)
        version_b.status = PromptVersionStatus.TESTING
        version_b.updated_at = now()
        await self._repository.update_prompt_version(version_b)

        return await self._repository.create_ab_test(
            ABTestRecord(
                id=new_id(), tenant_id=tenant_id, prompt_name=prompt_name,
                version_a_id=version_a_id, version_b_id=version_b_id,
            )
        )

    async def _get_ab_test(self, ab_test_id: str) -> ABTestRecord:
        record = await self._repository.get_ab_test(ab_test_id)
        if record is None:
            raise ABTestNotFoundError(ab_test_id)
        return record

    async def evaluate(self, ab_test_id: str) -> ABTestResult:
        ab_test = await self._get_ab_test(ab_test_id)
        version_a = await self._get_version(ab_test.version_a_id)
        version_b = await self._get_version(ab_test.version_b_id)

        scores_a = await self._evaluation_framework.list_scores(
            tenant_id=ab_test.tenant_id, agent_ref=evaluation_ref(version_a.prompt_name, version_a.version),
        )
        scores_b = await self._evaluation_framework.list_scores(
            tenant_id=ab_test.tenant_id, agent_ref=evaluation_ref(version_b.prompt_name, version_b.version),
        )
        n_a, n_b = len(scores_a), len(scores_b)

        if n_a < self._min_sample_size_per_arm or n_b < self._min_sample_size_per_arm:
            return ABTestResult(
                sample_size_a=n_a, sample_size_b=n_b, pass_rate_a=None, pass_rate_b=None, p_value=None,
                significant=False, winner_version_id=None,
                reason=(
                    f"insufficient_data: {n_a}/{self._min_sample_size_per_arm} (a), "
                    f"{n_b}/{self._min_sample_size_per_arm} (b) required samples per arm"
                ),
            )

        passed_a = sum(1 for s in scores_a if s.get("passed"))
        passed_b = sum(1 for s in scores_b if s.get("passed"))
        pass_rate_a, pass_rate_b = passed_a / n_a, passed_b / n_b
        _, p_value = two_proportion_z_test(passed_a, n_a, passed_b, n_b)

        significant = p_value < self._significance_level
        if not significant:
            return ABTestResult(
                sample_size_a=n_a, sample_size_b=n_b, pass_rate_a=pass_rate_a, pass_rate_b=pass_rate_b,
                p_value=p_value, significant=False, winner_version_id=None,
                reason=f"not significant: p={p_value:.4f} >= {self._significance_level}",
            )

        winner_id = ab_test.version_a_id if pass_rate_a > pass_rate_b else ab_test.version_b_id
        return ABTestResult(
            sample_size_a=n_a, sample_size_b=n_b, pass_rate_a=pass_rate_a, pass_rate_b=pass_rate_b,
            p_value=p_value, significant=True, winner_version_id=winner_id,
            reason=f"significant: p={p_value:.4f} < {self._significance_level}",
        )

    async def conclude(self, ab_test_id: str) -> ABTestRecord:
        ab_test = await self._get_ab_test(ab_test_id)
        result = await self.evaluate(ab_test_id)
        if not result.significant:
            raise ABTestNotConclusiveError(result.reason)

        winner_id = result.winner_version_id
        loser_id = ab_test.version_b_id if winner_id == ab_test.version_a_id else ab_test.version_a_id
        winner_pass_rate = result.pass_rate_a if winner_id == ab_test.version_a_id else result.pass_rate_b
        winner_sample_size = result.sample_size_a if winner_id == ab_test.version_a_id else result.sample_size_b

        winner = await self._get_version(winner_id)
        loser = await self._get_version(loser_id)

        # A clear statistical winner can still have failed its own most recent real
        # evaluation run (e.g. a faithfulness regression the A/B pass-rate comparison
        # alone wouldn't catch) -- Evaluation Framework's own `/gate` is the platform's
        # single source of truth for "did this version's evaluation actually pass,"
        # so `conclude` always re-checks it fresh here, the same as it always re-runs
        # `evaluate()` above rather than trusting an earlier verdict. `None` means no
        # eval run exists yet for this version -- not a failure, since there's nothing
        # to gate on.
        gate_result = await self._evaluation_framework.gate_latest_run(
            tenant_id=ab_test.tenant_id, agent_ref=evaluation_ref(winner.prompt_name, winner.version),
        )
        if gate_result is not None and not gate_result.get("overall_passed", True):
            raise EvaluationGateFailedError(gate_result.get("blocking_failures", []))

        previous_active = await self._repository.get_active_prompt_version(
            tenant_id=ab_test.tenant_id, prompt_name=ab_test.prompt_name,
        )
        if previous_active is not None and previous_active.id != winner.id:
            previous_active.status = PromptVersionStatus.ARCHIVED
            previous_active.updated_at = now()
            await self._repository.update_prompt_version(previous_active)

        winner.status = PromptVersionStatus.ACTIVE
        winner.promoted_pass_rate = winner_pass_rate
        winner.promoted_sample_size = winner_sample_size
        winner.updated_at = now()
        await self._repository.update_prompt_version(winner)

        loser.status = PromptVersionStatus.ARCHIVED
        loser.updated_at = now()
        await self._repository.update_prompt_version(loser)

        ab_test.status = ABTestStatus.CONCLUDED
        ab_test.winner_version_id = winner_id
        ab_test.p_value = result.p_value
        ab_test.sample_size_a = result.sample_size_a
        ab_test.sample_size_b = result.sample_size_b
        ab_test.concluded_at = now()
        return await self._repository.update_ab_test(ab_test)
