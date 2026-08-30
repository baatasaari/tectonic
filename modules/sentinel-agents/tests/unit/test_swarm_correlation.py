from datetime import UTC, datetime, timedelta

from sentinel_agents.core.swarm_correlation import (
    ModerateDeviationEvent,
    SwarmWindowTracker,
    detect,
)


def _event(agent_ref: str, z: float, t: datetime) -> ModerateDeviationEvent:
    return ModerateDeviationEvent(agent_ref=agent_ref, action_type="tool_call", z_score=z, timestamp=t)


def test_no_swarm_when_below_min_agents():
    now = datetime.now(UTC)
    events = [_event("a", 2.0, now), _event("b", 2.0, now)]
    result = detect(events, window_seconds=300, min_agents=3, reference_time=now)
    assert result is None


def test_swarm_detected_when_min_agents_reached():
    now = datetime.now(UTC)
    events = [_event("a", 2.0, now), _event("b", 2.5, now), _event("c", 3.0, now)]
    result = detect(events, window_seconds=300, min_agents=3, reference_time=now)
    assert result is not None
    assert set(result.agent_refs) == {"a", "b", "c"}


def test_events_outside_window_excluded():
    now = datetime.now(UTC)
    stale = now - timedelta(seconds=600)
    events = [_event("a", 2.0, stale), _event("b", 2.0, now), _event("c", 2.0, now)]
    result = detect(events, window_seconds=300, min_agents=3, reference_time=now)
    assert result is None


def test_same_agent_multiple_events_counts_once():
    now = datetime.now(UTC)
    events = [_event("a", 2.0, now), _event("a", 2.5, now), _event("b", 2.0, now)]
    result = detect(events, window_seconds=300, min_agents=2, reference_time=now)
    assert result is not None
    assert set(result.agent_refs) == {"a", "b"}


def test_window_tracker_prunes_old_events():
    tracker = SwarmWindowTracker()
    now = datetime.now(UTC)
    tracker.record(_event("a", 2.0, now - timedelta(seconds=600)))
    tracker.prune(now, window_seconds=300)
    tracker.record(_event("b", 2.0, now))
    tracker.record(_event("c", 2.0, now))
    result = tracker.detect(window_seconds=300, min_agents=3, reference_time=now)
    assert result is None  # only b, c remain — "a" was pruned


def test_window_tracker_detects_across_multiple_record_calls():
    tracker = SwarmWindowTracker()
    now = datetime.now(UTC)
    for agent in ("a", "b", "c"):
        tracker.record(_event(agent, 2.0, now))
    result = tracker.detect(window_seconds=300, min_agents=3, reference_time=now)
    assert result is not None
