import pytest

from tool_orchestration.core.domain import ReliabilityScoreRecord
from tool_orchestration.core.reliability_scorer import ReliabilityScorer


def test_first_update_with_no_prior_score_starts_from_defaults():
    scorer = ReliabilityScorer()
    updated = scorer.update(None, "t1", success=True, latency_ms=100.0)
    assert updated.tool_id == "t1"
    assert 0.0 <= updated.rolling_success_rate <= 1.0


def test_repeated_failures_drag_success_rate_down():
    scorer = ReliabilityScorer()
    score = ReliabilityScoreRecord(tool_id="t1", rolling_success_rate=1.0)
    for _ in range(10):
        score = scorer.update(score, "t1", success=False, latency_ms=50.0)
    assert score.rolling_success_rate < 0.3


def test_success_rate_recovers_after_failures_stop():
    scorer = ReliabilityScorer()
    score = ReliabilityScoreRecord(tool_id="t1", rolling_success_rate=1.0)
    for _ in range(5):
        score = scorer.update(score, "t1", success=False, latency_ms=50.0)
    low_point = score.rolling_success_rate
    for _ in range(10):
        score = scorer.update(score, "t1", success=True, latency_ms=50.0)
    assert score.rolling_success_rate > low_point


def test_latency_tracked_as_rolling_average():
    scorer = ReliabilityScorer()
    score = ReliabilityScoreRecord(tool_id="t1", rolling_avg_latency_ms=0.0)
    for _ in range(20):
        score = scorer.update(score, "t1", success=True, latency_ms=200.0)
    assert score.rolling_avg_latency_ms == pytest.approx(200.0, rel=0.05)
