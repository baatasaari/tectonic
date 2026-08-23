from conversational_engine.config import HandoffConfig
from conversational_engine.core.domain import HandoffTriggerReason
from conversational_engine.core.handoff import HandoffTriggerEngine


def _engine(**overrides) -> HandoffTriggerEngine:
    return HandoffTriggerEngine(HandoffConfig(**overrides))


def test_explicit_request_wins_over_everything_else():
    engine = _engine(emotion_score_threshold=0.99, repeated_refusal_threshold=99)
    decision = engine.evaluate(emotion_score=0.0, explicit_request=True, consecutive_refusals=0)
    assert decision.trigger is True
    assert decision.reason == HandoffTriggerReason.EXPLICIT


def test_high_emotion_triggers_handoff():
    engine = _engine(emotion_score_threshold=0.75)
    decision = engine.evaluate(emotion_score=0.8, explicit_request=False, consecutive_refusals=0)
    assert decision.trigger is True
    assert decision.reason == HandoffTriggerReason.EMOTION


def test_repeated_refusals_trigger_handoff():
    engine = _engine(repeated_refusal_threshold=3)
    decision = engine.evaluate(emotion_score=0.0, explicit_request=False, consecutive_refusals=3)
    assert decision.trigger is True
    assert decision.reason == HandoffTriggerReason.REPEATED_REFUSAL


def test_below_all_thresholds_does_not_trigger():
    engine = _engine(emotion_score_threshold=0.75, repeated_refusal_threshold=3)
    decision = engine.evaluate(emotion_score=0.5, explicit_request=False, consecutive_refusals=1)
    assert decision.trigger is False
    assert decision.reason is None
