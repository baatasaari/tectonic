from intent_detection.core.compositional_decomposer import CompositionalDecomposer


def test_single_intent_no_signal():
    assert CompositionalDecomposer().has_multi_intent_signal("check my balance") is False


def test_two_substantial_clauses_joined_by_and_signals():
    text = "update my mailing address and check my mortgage balance"
    assert CompositionalDecomposer().has_multi_intent_signal(text) is True


def test_semicolon_separated_clauses_signals():
    text = "close my account; also cancel my card"
    assert CompositionalDecomposer().has_multi_intent_signal(text) is True


def test_trivial_conjunction_without_two_substantial_clauses_does_not_signal():
    assert CompositionalDecomposer().has_multi_intent_signal("fish and chips") is False


def test_short_fragment_after_conjunction_does_not_count():
    # "and go" is only one word after stripping the conjunction — too
    # thin to plausibly carry its own intent.
    assert CompositionalDecomposer().has_multi_intent_signal("check my balance and go") is False
