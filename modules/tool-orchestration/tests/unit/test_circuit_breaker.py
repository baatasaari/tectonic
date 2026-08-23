from datetime import timedelta

from tool_orchestration.config import CircuitBreakerConfig
from tool_orchestration.core.circuit_breaker import CircuitBreaker
from tool_orchestration.core.domain import (
    CircuitBreakerStateRecord,
    CircuitState,
    ReliabilityScoreRecord,
    now,
)


def _score(success_rate: float) -> ReliabilityScoreRecord:
    return ReliabilityScoreRecord(tool_id="t1", rolling_success_rate=success_rate)


def test_closed_allows_calls():
    cb = CircuitBreaker(CircuitBreakerConfig())
    state = CircuitBreakerStateRecord(tool_id="t1", state=CircuitState.CLOSED)
    allowed, new_state = cb.may_call(state)
    assert allowed is True
    assert new_state.state == CircuitState.CLOSED


def test_trips_open_when_failure_rate_exceeds_threshold():
    cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=0.5))
    state = CircuitBreakerStateRecord(tool_id="t1", state=CircuitState.CLOSED)
    new_state = cb.record_result(state, _score(success_rate=0.3), success=False)  # failure rate 0.7 > 0.5
    assert new_state.state == CircuitState.OPEN
    assert new_state.opened_at is not None
    assert new_state.next_retry_at is not None


def test_stays_closed_when_failure_rate_within_threshold():
    cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=0.5))
    state = CircuitBreakerStateRecord(tool_id="t1", state=CircuitState.CLOSED)
    new_state = cb.record_result(state, _score(success_rate=0.9), success=True)
    assert new_state.state == CircuitState.CLOSED


def test_open_rejects_calls_before_retry_window():
    cb = CircuitBreaker(CircuitBreakerConfig(open_duration_seconds=60))
    state = CircuitBreakerStateRecord(
        tool_id="t1", state=CircuitState.OPEN, opened_at=now(), next_retry_at=now() + timedelta(seconds=60)
    )
    allowed, new_state = cb.may_call(state)
    assert allowed is False
    assert new_state.state == CircuitState.OPEN


def test_open_transitions_to_half_open_after_retry_window():
    cb = CircuitBreaker(CircuitBreakerConfig())
    state = CircuitBreakerStateRecord(
        tool_id="t1", state=CircuitState.OPEN, opened_at=now() - timedelta(seconds=120), next_retry_at=now() - timedelta(seconds=1)
    )
    allowed, new_state = cb.may_call(state)
    assert allowed is True
    assert new_state.state == CircuitState.HALF_OPEN


def test_half_open_probe_success_closes_circuit():
    cb = CircuitBreaker(CircuitBreakerConfig())
    state = CircuitBreakerStateRecord(tool_id="t1", state=CircuitState.HALF_OPEN)
    new_state = cb.record_result(state, _score(success_rate=1.0), success=True)
    assert new_state.state == CircuitState.CLOSED
    assert new_state.opened_at is None


def test_half_open_probe_failure_reopens_circuit():
    cb = CircuitBreaker(CircuitBreakerConfig())
    state = CircuitBreakerStateRecord(tool_id="t1", state=CircuitState.HALF_OPEN)
    new_state = cb.record_result(state, _score(success_rate=0.0), success=False)
    assert new_state.state == CircuitState.OPEN
