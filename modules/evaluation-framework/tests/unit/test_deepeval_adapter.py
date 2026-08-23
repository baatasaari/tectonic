"""Exercises the real `deepeval.metrics.FaithfulnessMetric` pipeline —
not a mock of DeepEval itself, only its backing LLM call — via
`StubLLMGatewayClient.complete()`'s scripted responder. If DeepEval
changes its internal prompt templates in a way this scripting no longer
matches, these tests fail loudly rather than silently passing against a
fake that stopped reflecting the real library.
"""
import pytest

from evaluation_framework.core.deepeval_adapter import DeepEvalFaithfulnessMetric, resolve_metric
from evaluation_framework.core.metric_adapters import CoherenceMetric


async def test_deepeval_faithfulness_scores_high_for_fully_grounded_output(harness):
    metric = DeepEvalFaithfulnessMetric()
    score = await metric.compute(
        "the account balance is 500 dollars today",
        {"context": "the account balance is 500 dollars today"},
        harness.llm_gateway,
    )
    assert score == 1.0


async def test_deepeval_faithfulness_scores_low_for_unsupported_claim(harness):
    metric = DeepEvalFaithfulnessMetric()
    score = await metric.compute(
        "the account balance is 500 dollars. the account is scheduled for closure next week.",
        {"context": "the account balance is 500 dollars as of today"},
        harness.llm_gateway,
    )
    assert score < 1.0


async def test_deepeval_faithfulness_zero_when_no_context(harness):
    metric = DeepEvalFaithfulnessMetric()
    score = await metric.compute("anything", {}, harness.llm_gateway)
    assert score == 0.0


async def test_deepeval_faithfulness_calls_the_real_llm_gateway_completion(harness):
    metric = DeepEvalFaithfulnessMetric()
    await metric.compute("the balance is 500 dollars", {"context": "the balance is 500 dollars"}, harness.llm_gateway)
    # Truths + Claims + Verdicts, at minimum — a real multi-step DeepEval pipeline,
    # not a single canned call.
    assert len(harness.llm_gateway.completion_calls) >= 3


async def test_deepeval_faithfulness_falls_back_to_heuristic_on_llm_gateway_failure():
    class BrokenLLMGatewayClient:
        async def judge(self, agent_output, metric_name, reference_data):
            raise AssertionError("judge() should not be called by the faithfulness metric")

        async def complete(self, prompt):
            raise RuntimeError("LLM Gateway unreachable")

    metric = DeepEvalFaithfulnessMetric()
    score = await metric.compute(
        "the balance is 500 dollars today", {"context": "the balance is 500 dollars today"}, BrokenLLMGatewayClient(),
    )
    # The fallback is the heuristic term-overlap score for identical text: 1.0.
    assert score == pytest.approx(1.0)


async def test_resolve_metric_uses_deepeval_for_faithfulness():
    assert isinstance(resolve_metric("faithfulness"), DeepEvalFaithfulnessMetric)


async def test_resolve_metric_delegates_other_metrics_to_metric_adapters():
    assert isinstance(resolve_metric("coherence"), CoherenceMetric)
