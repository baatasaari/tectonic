from sentinel_agents.core.baseliner import MIN_SAMPLES, update_and_check


def test_no_deviation_flagged_before_min_samples():
    baseline = None
    for _ in range(MIN_SAMPLES - 1):
        result = update_and_check(baseline, "agent-1", "tool_call", 10.0, "medium")
        baseline = result.baseline
    assert result.deviation_detected is False


def test_consistent_values_never_deviate():
    baseline = None
    result = None
    for _ in range(20):
        result = update_and_check(baseline, "agent-1", "tool_call", 10.0, "medium")
        baseline = result.baseline
    assert result.deviation_detected is False
    assert result.z_score == 0.0


def test_outlier_after_stable_history_flagged():
    baseline = None
    for _ in range(10):
        result = update_and_check(baseline, "agent-1", "tool_call", 10.0, "medium")
        baseline = result.baseline
    # A wildly different value after a tight, stable history should be
    # flagged as a deviation.
    result = update_and_check(baseline, "agent-1", "tool_call", 1000.0, "medium")
    assert result.deviation_detected is True
    assert result.z_score == float("inf")


def test_higher_sensitivity_flags_smaller_deviations():
    import random

    random.seed(42)
    baseline = None
    for _ in range(30):
        result = update_and_check(baseline, "agent-1", "tool_call", 10.0 + random.uniform(-1, 1), "medium")
        baseline = result.baseline

    moderate_value = 13.0
    low = update_and_check(baseline, "agent-1", "tool_call", moderate_value, "low")
    high = update_and_check(baseline, "agent-1", "tool_call", moderate_value, "high")
    # Same z-score either way; "high" sensitivity has a lower bar to clear.
    assert low.z_score == high.z_score
    if low.deviation_detected:
        assert high.deviation_detected is True


def test_baseline_continues_learning_after_update():
    result1 = update_and_check(None, "agent-1", "tool_call", 5.0, "medium")
    result2 = update_and_check(result1.baseline, "agent-1", "tool_call", 7.0, "medium")
    assert result2.baseline.sample_count == 2
    assert result2.baseline.mean == 6.0
