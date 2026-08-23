from intent_detection.core.domain import IntentDefinition
from intent_detection.core.primary_classifier import PrimaryClassifier

_INTENTS = [
    IntentDefinition(name="check_balance", examples=["what is my account balance", "check my balance"]),
    IntentDefinition(name="update_address", examples=["update my mailing address", "change my address"]),
]


def test_close_match_scores_highest_for_correct_intent():
    scored = PrimaryClassifier().classify("check my balance please", _INTENTS)
    assert scored[0].name == "check_balance"
    assert scored[0].confidence > scored[1].confidence


def test_unrelated_text_scores_low_for_everything():
    scored = PrimaryClassifier().classify("turn on the living room lights", _INTENTS)
    assert all(s.confidence < 0.3 for s in scored)


def test_intent_without_examples_scores_zero():
    intents = [IntentDefinition(name="no_examples", examples=[])]
    scored = PrimaryClassifier().classify("anything", intents)
    assert scored[0].confidence == 0.0


def test_results_sorted_descending_by_confidence():
    scored = PrimaryClassifier().classify("update my address", _INTENTS)
    confidences = [s.confidence for s in scored]
    assert confidences == sorted(confidences, reverse=True)
