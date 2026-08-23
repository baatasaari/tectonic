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
