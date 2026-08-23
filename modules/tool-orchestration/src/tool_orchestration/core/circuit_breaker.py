"""Circuit Breaker (LLD §2.2, §3.5, §3.6): trips on repeated tool failure,
prevents cascading retries against a known-bad tool. Pure state-transition
logic here; the Redis-backed CircuitBreakerStore (or an in-memory fake) owns
persistence, per the same ports-and-adapters split every other module uses.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from tool_orchestration.config import CircuitBreakerConfig
from tool_orchestration.core.domain import (
    CircuitBreakerStateRecord,
    CircuitState,
    ReliabilityScoreRecord,
    now,
)
from tool_orchestration.telemetry.metrics import tool_circuit_breaker_state

_STATE_METRIC_VALUE = {CircuitState.CLOSED: 0, CircuitState.HALF_OPEN: 1, CircuitState.OPEN: 2}


class CircuitBreaker:
    def __init__(self, config: CircuitBreakerConfig) -> None:
        self.config = config

    def may_call(self, state: CircuitBreakerStateRecord) -> tuple[bool, CircuitBreakerStateRecord]:
        """Returns (allowed, possibly-transitioned state). A half-open probe
        is allowed exactly once per retry window — the caller that gets
        `allowed=True` while transitioning open->half_open is the probe."""
        if state.state == CircuitState.CLOSED:
            return True, state
        if state.state == CircuitState.OPEN:
            if state.next_retry_at is not None and now() >= state.next_retry_at:
                return True, replace(state, state=CircuitState.HALF_OPEN)
            return False, state
        # half_open: only one probe in flight at a time is the ideal, but
        # without a lock we allow probes through — record_result below is
        # what actually moves the state, so a second concurrent probe just
        # duplicates one call rather than corrupting the state machine.
        return True, state

    def record_result(
        self, state: CircuitBreakerStateRecord, reliability: ReliabilityScoreRecord, success: bool
    ) -> CircuitBreakerStateRecord:
        tool_circuit_breaker_state.labels(tool_id=state.tool_id).set(_STATE_METRIC_VALUE[state.state])

        if state.state == CircuitState.HALF_OPEN:
            if success:
                new_state = replace(state, state=CircuitState.CLOSED, opened_at=None, next_retry_at=None)
            else:
                new_state = self._trip_open(state)
            tool_circuit_breaker_state.labels(tool_id=state.tool_id).set(_STATE_METRIC_VALUE[new_state.state])
            return new_state

        if state.state == CircuitState.CLOSED:
            failure_rate = 1.0 - reliability.rolling_success_rate
            if failure_rate > self.config.failure_threshold:
                new_state = self._trip_open(state)
                tool_circuit_breaker_state.labels(tool_id=state.tool_id).set(_STATE_METRIC_VALUE[new_state.state])
                return new_state
            return state

        # already open and a call somehow completed (e.g. a stale probe) —
        # leave the timer alone rather than extending the outage on success,
        # or re-trip cleanly on failure.
        if success:
            return state
        return self._trip_open(state)

    def _trip_open(self, state: CircuitBreakerStateRecord) -> CircuitBreakerStateRecord:
        opened = now()
        return replace(
            state,
            state=CircuitState.OPEN,
            opened_at=opened,
            next_retry_at=opened + timedelta(seconds=self.config.open_duration_seconds),
        )
