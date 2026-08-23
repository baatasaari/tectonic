from guardrails.core.groundedness_checker import is_grounded, score


def test_identical_text_fully_grounded():
    assert score("the sky is blue", "the sky is blue") == 1.0


def test_unrelated_text_scores_low():
    assert score("quarterly revenue grew 12 percent", "the cat sat on the mat") < 0.2


def test_is_grounded_respects_threshold():
    context = "Our Q3 revenue grew by 12 percent driven by strong enterprise sales"
    grounded_output = "Q3 revenue grew 12 percent due to enterprise sales"
    ungrounded_output = "Our office moved to a new building downtown"
    assert is_grounded(grounded_output, context, threshold=0.5) is True
    assert is_grounded(ungrounded_output, context, threshold=0.5) is False
