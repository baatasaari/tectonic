"""Tests for core/trust_score_calculator.py -- the weighted-average /
graceful-degradation matrix this module's own trust score depends on."""
from __future__ import annotations

import pytest

from agent_cards.core.domain import AgentCardRecord
from agent_cards.core.fakes import StubEvaluationFrameworkClient, StubRegulatoryComplianceClient


def _card(**overrides) -> AgentCardRecord:
    defaults = {"id": "c1", "tenant_id": "acme", "agent_ref": "agent-1", "name": "a", "description": "", "url": "http://a"}
    defaults.update(overrides)
    return AgentCardRecord(**defaults)


async def test_both_signals_available_produces_a_weighted_average(harness_factory):
    evalfw = StubEvaluationFrameworkClient(scores=[{"score": 0.8, "threshold": 1.0}])
    regcomp = StubRegulatoryComplianceClient(coverage_percentage=50.0)
    harness = harness_factory(evaluation_framework=evalfw, regulatory_compliance=regcomp, performance_weight=0.6, compliance_weight=0.4)
    card = await harness.repository.create_card(_card())

    breakdown = await harness.trust_score_calculator.recompute(card)

    assert breakdown.performance_score == 0.8
    assert breakdown.compliance_score == 0.5
    assert breakdown.trust_score == pytest.approx(0.8 * 0.6 + 0.5 * 0.4)
    assert breakdown.insufficient_data is False


async def test_only_performance_available_uses_performance_alone(harness_factory):
    evalfw = StubEvaluationFrameworkClient(scores=[{"score": 0.9, "threshold": 1.0}])
    regcomp = StubRegulatoryComplianceClient(coverage_percentage=None)
    harness = harness_factory(evaluation_framework=evalfw, regulatory_compliance=regcomp)
    card = await harness.repository.create_card(_card())

    breakdown = await harness.trust_score_calculator.recompute(card)

    assert breakdown.compliance_score is None
    assert breakdown.trust_score == pytest.approx(0.9)


async def test_only_compliance_available_uses_compliance_alone(harness_factory):
    evalfw = StubEvaluationFrameworkClient(scores=[])
    regcomp = StubRegulatoryComplianceClient(coverage_percentage=80.0)
    harness = harness_factory(evaluation_framework=evalfw, regulatory_compliance=regcomp)
    card = await harness.repository.create_card(_card())

    breakdown = await harness.trust_score_calculator.recompute(card)

    assert breakdown.performance_score is None
    assert breakdown.trust_score == pytest.approx(0.8)


async def test_neither_signal_available_leaves_trust_score_null(harness_factory):
    evalfw = StubEvaluationFrameworkClient(scores=[])
    regcomp = StubRegulatoryComplianceClient(coverage_percentage=None)
    harness = harness_factory(evaluation_framework=evalfw, regulatory_compliance=regcomp)
    card = await harness.repository.create_card(_card())

    breakdown = await harness.trust_score_calculator.recompute(card)

    assert breakdown.trust_score is None
    assert breakdown.insufficient_data is True


async def test_a_down_peer_degrades_gracefully_instead_of_raising(harness_factory):
    class BoomEvaluationFrameworkClient:
        async def list_scores(self, *, tenant_id, agent_ref):
            raise ConnectionError("evaluation-framework unreachable")

    regcomp = StubRegulatoryComplianceClient(coverage_percentage=100.0)
    harness = harness_factory(evaluation_framework=BoomEvaluationFrameworkClient(), regulatory_compliance=regcomp)
    card = await harness.repository.create_card(_card())

    breakdown = await harness.trust_score_calculator.recompute(card)

    assert breakdown.performance_score is None
    assert breakdown.compliance_score == 1.0
    assert breakdown.trust_score == 1.0


async def test_recompute_persists_the_new_score_on_the_card(harness_factory):
    evalfw = StubEvaluationFrameworkClient(scores=[{"score": 1.0, "threshold": 1.0}])
    regcomp = StubRegulatoryComplianceClient(coverage_percentage=100.0)
    harness = harness_factory(evaluation_framework=evalfw, regulatory_compliance=regcomp)
    card = await harness.repository.create_card(_card())

    await harness.trust_score_calculator.recompute(card)

    persisted = await harness.repository.get_card(card.id)
    assert persisted.trust_score == 1.0
    assert persisted.trust_score_computed_at is not None


async def test_a_score_above_its_threshold_is_clamped_to_1(harness_factory):
    evalfw = StubEvaluationFrameworkClient(scores=[{"score": 2.0, "threshold": 1.0}])
    regcomp = StubRegulatoryComplianceClient(coverage_percentage=None)
    harness = harness_factory(evaluation_framework=evalfw, regulatory_compliance=regcomp)
    card = await harness.repository.create_card(_card())

    breakdown = await harness.trust_score_calculator.recompute(card)

    assert breakdown.performance_score == 1.0


async def test_zero_weight_configuration_falls_back_to_an_unweighted_mean(harness_factory):
    evalfw = StubEvaluationFrameworkClient(scores=[{"score": 0.4, "threshold": 1.0}])
    regcomp = StubRegulatoryComplianceClient(coverage_percentage=80.0)
    harness = harness_factory(evaluation_framework=evalfw, regulatory_compliance=regcomp, performance_weight=0.0, compliance_weight=0.0)
    card = await harness.repository.create_card(_card())

    breakdown = await harness.trust_score_calculator.recompute(card)

    assert breakdown.trust_score == pytest.approx((0.4 + 0.8) / 2)
