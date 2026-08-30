from datetime import timedelta

from evaluation_framework.core.domain import MetricScoreRecord, new_id, now


async def test_evaluate_runs_all_metrics_and_persists_scores(harness):
    run, scores = await harness.evaluator.evaluate(
        "t1", "agent-1", "the balance is 500 dollars", {"context": "the balance is 500 dollars today"},
        ["faithfulness", "coherence"], "ci_cd",
    )
    assert run.status.value == "completed"
    assert run.completed_at is not None
    assert {s.metric_name for s in scores} == {"faithfulness", "coherence"}

    persisted = await harness.repository.list_metric_scores_for_run(run.id)
    assert len(persisted) == 2


async def test_evaluate_marks_score_passed_against_threshold(harness):
    _run, scores = await harness.evaluator.evaluate(
        "t1", "agent-1", "irrelevant text with no overlap", {"context": "something completely different"},
        ["faithfulness"], "ci_cd",
    )
    assert scores[0].passed is False  # faithfulness threshold is 0.5, similarity is ~0.0


async def test_evaluate_uses_custom_thresholds_override(harness):
    _run, scores = await harness.evaluator.evaluate(
        "t1", "agent-1", "output", {"actual_tool_sequence": [{"tool": "x", "status": "ok"}]},
        ["tool_trace_correctness"], "ci_cd", custom_thresholds={"tool_trace_correctness": 1.1},
    )
    assert scores[0].threshold == 1.1
    assert scores[0].passed is False  # score of 1.0 can never clear a 1.1 threshold


async def test_evaluate_llm_judge_metric_calls_gateway_and_persists(harness):
    _run, scores = await harness.evaluator.evaluate(
        "t1", "agent-1", "output", {}, ["custom_hallucination_check"], "production_sample",
    )
    assert scores[0].metric_name == "custom_hallucination_check"
    assert scores[0].score == harness.llm_gateway.judged_score
    assert len(harness.llm_gateway.calls) == 1


async def test_evaluate_records_agent_ref_and_tenant_on_scores(harness):
    _run, scores = await harness.evaluator.evaluate("t1", "agent-9", "x", {}, ["coherence"], "ci_cd")
    assert scores[0].tenant_id == "t1"
    assert scores[0].agent_ref == "agent-9"


async def _seed_score(harness, *, age_seconds: int):
    record = MetricScoreRecord(
        id=new_id(), eval_run_id="run-1", tenant_id="t1", agent_ref="agent-1", metric_name="coherence",
        score=0.9, threshold=0.5, passed=True, created_at=now() - timedelta(seconds=age_seconds),
    )
    return await harness.repository.create_metric_score(record)


async def test_list_metric_scores_for_tenant_paginates_newest_first(harness):
    oldest = await _seed_score(harness, age_seconds=200)
    middle = await _seed_score(harness, age_seconds=100)
    newest = await _seed_score(harness, age_seconds=0)

    page1, total = await harness.repository.list_metric_scores_for_tenant("t1", limit=2, offset=0)
    assert total == 3
    assert [s.id for s in page1] == [newest.id, middle.id]

    page2, total = await harness.repository.list_metric_scores_for_tenant("t1", limit=2, offset=2)
    assert total == 3
    assert [s.id for s in page2] == [oldest.id]


async def test_list_metric_scores_for_tenant_empty_returns_no_error(harness):
    scores, total = await harness.repository.list_metric_scores_for_tenant("no-such-tenant")
    assert scores == []
    assert total == 0
