from evaluation_framework.core.metric_adapters import (
    CoherenceMetric,
    FinancialGuidanceComplianceMetric,
    HeuristicFaithfulnessMetric,
    LLMJudgeMetric,
    ToolTraceCorrectnessMetric,
    resolve_metric,
)


async def test_faithfulness_high_when_output_matches_context(harness):
    metric = HeuristicFaithfulnessMetric()
    score = await metric.compute(
        "the account balance is 500 dollars", {"context": "the account balance is 500 dollars today"}, harness.llm_gateway,
    )
    assert score > 0.7


async def test_faithfulness_zero_when_no_context(harness):
    metric = HeuristicFaithfulnessMetric()
    score = await metric.compute("anything", {}, harness.llm_gateway)
    assert score == 0.0


async def test_faithfulness_low_for_unrelated_output(harness):
    metric = HeuristicFaithfulnessMetric()
    score = await metric.compute("bananas are yellow", {"context": "quarterly revenue grew 12 percent"}, harness.llm_gateway)
    assert score < 0.2


async def test_coherence_penalizes_repeated_sentences(harness):
    metric = CoherenceMetric()
    repeated = "The system is ready. The system is ready. The system is ready."
    varied = "The system is ready. Deployment completed successfully. All checks passed."
    repeated_score = await metric.compute(repeated, {}, harness.llm_gateway)
    varied_score = await metric.compute(varied, {}, harness.llm_gateway)
    assert varied_score > repeated_score


async def test_coherence_empty_output_is_zero(harness):
    metric = CoherenceMetric()
    score = await metric.compute("", {}, harness.llm_gateway)
    assert score == 0.0


async def test_tool_trace_correctness_all_ok(harness):
    metric = ToolTraceCorrectnessMetric()
    trace = {"actual_tool_sequence": [{"tool": "lookup", "status": "ok"}, {"tool": "book", "status": "ok"}]}
    score = await metric.compute("x", trace, harness.llm_gateway)
    assert score == 1.0


async def test_tool_trace_correctness_with_errors(harness):
    metric = ToolTraceCorrectnessMetric()
    trace = {"actual_tool_sequence": [{"tool": "lookup", "status": "ok"}, {"tool": "book", "status": "error"}]}
    score = await metric.compute("x", trace, harness.llm_gateway)
    assert score == 0.5


async def test_tool_trace_correctness_no_calls_is_trivially_correct(harness):
    metric = ToolTraceCorrectnessMetric()
    score = await metric.compute("x", {}, harness.llm_gateway)
    assert score == 1.0


async def test_financial_guidance_compliance_with_disclaimer(harness):
    metric = FinancialGuidanceComplianceMetric()
    score = await metric.compute("This is not financial advice; consider your own risk tolerance.", {}, harness.llm_gateway)
    assert score == 1.0


async def test_financial_guidance_compliance_guarantee_claim_scores_zero(harness):
    metric = FinancialGuidanceComplianceMetric()
    score = await metric.compute("This fund offers a guaranteed return of 10% annually.", {}, harness.llm_gateway)
    assert score == 0.0


async def test_financial_guidance_compliance_neither(harness):
    metric = FinancialGuidanceComplianceMetric()
    score = await metric.compute("Here is some general market commentary.", {}, harness.llm_gateway)
    assert score == 0.5


async def test_resolve_metric_returns_known_heuristics():
    # metric_adapters' own resolve_metric still returns the heuristic for
    # "faithfulness" — deepeval_adapter.resolve_metric() is the one that overrides it
    # with the real DeepEval-backed metric; see test_deepeval_adapter.py.
    assert isinstance(resolve_metric("faithfulness"), HeuristicFaithfulnessMetric)
    assert isinstance(resolve_metric("coherence"), CoherenceMetric)
    assert isinstance(resolve_metric("tool_trace_correctness"), ToolTraceCorrectnessMetric)


async def test_resolve_metric_falls_back_to_llm_judge():
    metric = resolve_metric("hallucination_llm_judge")
    assert isinstance(metric, LLMJudgeMetric)


async def test_llm_judge_metric_calls_gateway(harness):
    metric = LLMJudgeMetric("custom_metric")
    score = await metric.compute("output text", {"k": "v"}, harness.llm_gateway)
    assert score == harness.llm_gateway.judged_score
    assert harness.llm_gateway.calls[0]["metric_name"] == "custom_metric"
