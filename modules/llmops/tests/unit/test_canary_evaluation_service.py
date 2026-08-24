"""Tests for core/canary_evaluation_service.py -- the sample-size/pass-rate gate matrix."""
from __future__ import annotations

from llmops.core.domain import ModelVersionRecord
from llmops.core.fakes import StubEvaluationFrameworkClient


def _version(**overrides) -> ModelVersionRecord:
    defaults = {"id": "v1", "tenant_id": "acme", "model_name": "chat-default", "version": "3", "artifact_ref": "openai/gpt-x"}
    defaults.update(overrides)
    return ModelVersionRecord(**defaults)


async def test_below_minimum_sample_size_is_insufficient_data_not_a_pass(harness_factory):
    evalfw = StubEvaluationFrameworkClient(scores=[{"score": 1.0, "threshold": 1.0, "passed": True}])
    harness = harness_factory(evaluation_framework=evalfw, min_sample_size=3)

    result = await harness.canary_evaluation_service.evaluate(_version())

    assert result.passed is False
    assert "insufficient_data" in result.reason
    assert result.pass_rate is None


async def test_a_low_pass_rate_fails_the_gate(harness_factory):
    scores = [{"passed": True}, {"passed": True}, {"passed": False}, {"passed": False}]
    evalfw = StubEvaluationFrameworkClient(scores=scores)
    harness = harness_factory(evaluation_framework=evalfw, min_sample_size=3, min_pass_rate=0.8)

    result = await harness.canary_evaluation_service.evaluate(_version())

    assert result.passed is False
    assert result.pass_rate == 0.5
    assert "below required" in result.reason


async def test_a_sufficient_sample_with_a_high_pass_rate_passes(harness_factory):
    scores = [{"passed": True}] * 9 + [{"passed": False}]
    evalfw = StubEvaluationFrameworkClient(scores=scores)
    harness = harness_factory(evaluation_framework=evalfw, min_sample_size=3, min_pass_rate=0.8)

    result = await harness.canary_evaluation_service.evaluate(_version())

    assert result.passed is True
    assert result.pass_rate == 0.9
    assert result.sample_size == 10


async def test_evaluation_ref_is_scoped_to_model_name_and_version(harness_factory):
    evalfw = StubEvaluationFrameworkClient(scores=[])
    harness = harness_factory(evaluation_framework=evalfw)

    await harness.canary_evaluation_service.evaluate(_version(model_name="chat-default", version="3"))

    assert evalfw.calls[0]["agent_ref"] == "model:chat-default:3"
