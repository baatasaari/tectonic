"""Tests for core/canary_health_calculator.py -- the weighted,
renormalize-over-available-signals health gate combining Evaluation
Framework's groundedness pass rate with FinOps's cost utilisation."""
from __future__ import annotations

from deployment_strategy.core.domain import DeploymentRecord
from deployment_strategy.core.fakes import StubEvaluationFrameworkClient, StubFinOpsClient

_PASSING_SCORES = [{"passed": True}] * 5
_FAILING_SCORES = [{"passed": False}] * 5


def _deployment(**overrides) -> DeploymentRecord:
    defaults = {
        "id": "d1", "tenant_id": "acme", "service_name": "conversational-engine",
        "build_ref": "v1.2.3", "target": "prod",
    }
    defaults.update(overrides)
    return DeploymentRecord(**defaults)


async def test_zero_signals_with_data_is_insufficient_data(harness_factory):
    h = harness_factory(evaluation_framework=StubEvaluationFrameworkClient(scores=[]))
    deployment = _deployment()  # no budget_policy_id -> cost signal excluded too

    result = await h.canary_health_calculator.evaluate(deployment)

    assert result.composite_score is None
    assert result.passed is False
    assert "insufficient_data" in result.reason


async def test_passes_on_groundedness_alone_when_cost_signal_is_not_configured(harness_factory):
    h = harness_factory(
        evaluation_framework=StubEvaluationFrameworkClient(scores=_PASSING_SCORES), min_groundedness_sample_size=3,
    )
    deployment = _deployment()  # no budget_policy_id

    result = await h.canary_health_calculator.evaluate(deployment)

    assert result.groundedness_score == 1.0
    assert result.cost_score is None
    assert result.composite_score == 1.0
    assert result.passed is True


async def test_fails_when_groundedness_pass_rate_is_low(harness_factory):
    h = harness_factory(
        evaluation_framework=StubEvaluationFrameworkClient(scores=_FAILING_SCORES), min_groundedness_sample_size=3,
        min_health_score=0.8,
    )
    deployment = _deployment()

    result = await h.canary_health_calculator.evaluate(deployment)

    assert result.groundedness_score == 0.0
    assert result.passed is False


async def test_combines_groundedness_and_cost_signals_when_both_present(harness_factory):
    h = harness_factory(
        evaluation_framework=StubEvaluationFrameworkClient(scores=_PASSING_SCORES),
        finops=StubFinOpsClient(utilisation_ratio=0.2), min_groundedness_sample_size=3,
        groundedness_weight=0.6, cost_weight=0.4,
    )
    deployment = _deployment(budget_policy_id="bp1")

    result = await h.canary_health_calculator.evaluate(deployment)

    # groundedness 1.0 * 0.6 + cost (1 - 0.2 = 0.8) * 0.4 = 0.92
    assert result.groundedness_score == 1.0
    assert result.cost_score == 0.8
    assert abs(result.composite_score - 0.92) < 1e-9
    assert result.passed is True


async def test_high_cost_utilisation_can_fail_an_otherwise_healthy_canary(harness_factory):
    h = harness_factory(
        evaluation_framework=StubEvaluationFrameworkClient(scores=_PASSING_SCORES),
        finops=StubFinOpsClient(utilisation_ratio=0.95), min_groundedness_sample_size=3,
        groundedness_weight=0.6, cost_weight=0.4, min_health_score=0.8,
    )
    deployment = _deployment(budget_policy_id="bp1")

    result = await h.canary_health_calculator.evaluate(deployment)

    # groundedness 1.0 * 0.6 + cost (1 - 0.95 = 0.05) * 0.4 = 0.62 < 0.8
    assert result.passed is False


async def test_cost_signal_is_excluded_not_penalized_when_budget_policy_is_unknown(harness_factory):
    h = harness_factory(
        evaluation_framework=StubEvaluationFrameworkClient(scores=_PASSING_SCORES),
        finops=StubFinOpsClient(utilisation_ratio=None), min_groundedness_sample_size=3,
    )
    deployment = _deployment(budget_policy_id="does-not-exist")

    result = await h.canary_health_calculator.evaluate(deployment)

    assert result.cost_score is None
    assert result.composite_score == 1.0  # renormalized to groundedness alone
    assert result.passed is True


async def test_a_failing_evaluation_framework_call_degrades_gracefully(harness_factory):
    class BoomEvaluationFrameworkClient:
        async def list_scores(self, *, tenant_id, agent_ref):
            raise RuntimeError("evaluation-framework is down")

    h = harness_factory(
        evaluation_framework=BoomEvaluationFrameworkClient(), finops=StubFinOpsClient(utilisation_ratio=0.1),
    )
    deployment = _deployment(budget_policy_id="bp1")

    result = await h.canary_health_calculator.evaluate(deployment)

    assert result.groundedness_score is None
    assert result.cost_score == 0.9
    assert result.composite_score == 0.9  # renormalized to cost alone
    assert result.passed is True


async def test_finops_client_is_only_called_when_a_budget_policy_id_is_set(harness_factory):
    finops = StubFinOpsClient(utilisation_ratio=0.1)
    h = harness_factory(evaluation_framework=StubEvaluationFrameworkClient(scores=_PASSING_SCORES), finops=finops)
    deployment = _deployment()  # no budget_policy_id

    await h.canary_health_calculator.evaluate(deployment)

    assert finops.calls == []
