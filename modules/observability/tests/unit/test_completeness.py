async def test_completeness_full_when_all_expected_spans_present(harness_factory):
    h = harness_factory(expected_spans={"support_flow": ["retrieve", "classify", "respond"]})
    for name in ("retrieve", "classify", "respond"):
        await h.add_span("t1", "trace-1", name, name, workflow_type="support_flow")

    result = await h.completeness_calculator.compute("t1")

    assert result.completeness_ratio == 1.0
    assert result.traces_with_known_shape == 1


async def test_completeness_partial_when_a_span_is_missing(harness_factory):
    h = harness_factory(expected_spans={"support_flow": ["retrieve", "classify", "respond"]})
    await h.add_span("t1", "trace-1", "retrieve", "retrieve", workflow_type="support_flow")
    await h.add_span("t1", "trace-1", "classify", "classify", workflow_type="support_flow")
    # "respond" never recorded — an instrumentation gap

    result = await h.completeness_calculator.compute("t1")

    assert result.completeness_ratio == 2 / 3


async def test_completeness_ignores_traces_with_unknown_workflow_type(harness_factory):
    h = harness_factory(expected_spans={"support_flow": ["retrieve", "respond"]})
    await h.add_span("t1", "trace-1", "step", "step", workflow_type="unmapped_flow")

    result = await h.completeness_calculator.compute("t1")

    assert result.completeness_ratio == 1.0  # nothing to compare, so no incompleteness to report
    assert result.traces_with_known_shape == 0
    assert result.traces_checked == 1


async def test_completeness_averages_across_multiple_traces(harness_factory):
    h = harness_factory(expected_spans={"support_flow": ["a", "b"]})
    await h.add_span("t1", "trace-1", "a", "a", workflow_type="support_flow")
    await h.add_span("t1", "trace-1", "b", "b", workflow_type="support_flow")  # trace-1: complete (1.0)
    await h.add_span("t1", "trace-2", "a", "a", workflow_type="support_flow")  # trace-2: half (0.5)

    result = await h.completeness_calculator.compute("t1")

    assert result.completeness_ratio == 0.75


async def test_completeness_scoped_by_tenant(harness_factory):
    h = harness_factory(expected_spans={"support_flow": ["a", "b"]})
    await h.add_span("t1", "trace-1", "a", "a", workflow_type="support_flow")
    await h.add_span("t2", "trace-1", "a", "a", workflow_type="support_flow")
    await h.add_span("t2", "trace-1", "b", "b", workflow_type="support_flow")

    result_t1 = await h.completeness_calculator.compute("t1")
    result_t2 = await h.completeness_calculator.compute("t2")

    assert result_t1.completeness_ratio == 0.5
    assert result_t2.completeness_ratio == 1.0
