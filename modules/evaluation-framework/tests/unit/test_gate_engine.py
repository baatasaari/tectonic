import pytest

from evaluation_framework.core.domain import EvalRunNotFoundError


async def test_gate_passes_when_all_scores_pass(harness):
    run, _scores = await harness.evaluator.evaluate(
        "t1", "agent-1", "the balance is 500 dollars", {"context": "the balance is 500 dollars today"},
        ["faithfulness"], "ci_cd",
    )
    result = await harness.gate_engine.gate("t1", run.id)
    assert result.overall_passed is True
    assert result.blocking_failures == []


async def test_gate_fails_lists_blocking_metrics(harness):
    run, _scores = await harness.evaluator.evaluate(
        "t1", "agent-1", "irrelevant", {"context": "something else entirely"}, ["faithfulness"], "ci_cd",
    )
    result = await harness.gate_engine.gate("t1", run.id)
    assert result.overall_passed is False
    assert "faithfulness" in result.blocking_failures


async def test_gate_missing_eval_run_raises(harness):
    with pytest.raises(EvalRunNotFoundError):
        await harness.gate_engine.gate("t1", "does-not-exist")


async def test_gate_wrong_tenant_raises_not_found(harness):
    run, _scores = await harness.evaluator.evaluate("t1", "agent-1", "x", {}, ["coherence"], "ci_cd")
    with pytest.raises(EvalRunNotFoundError):
        await harness.gate_engine.gate("other-tenant", run.id)


async def test_gate_records_environment(harness):
    run, _scores = await harness.evaluator.evaluate("t1", "agent-1", "x", {}, ["coherence"], "ci_cd")
    result = await harness.gate_engine.gate("t1", run.id, environment="staging")
    assert result.environment == "staging"
