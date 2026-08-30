from short_term_memory.core.salience_scorer import score


def test_empty_content_scores_zero():
    assert score("") == 0.0
    assert score("   ") == 0.0


def test_plain_chatter_scores_low():
    assert score("yeah sounds good, see you then") < 0.3


def test_numbers_increase_score():
    plain = score("let's meet up soon")
    with_number = score("let's meet up around 5pm soon")
    assert with_number > plain


def test_commitment_phrase_scores_high():
    assert score("I will send the report by Friday") >= 0.4


def test_explicit_remember_cue_scores_highest():
    assert score("Please remember this: the account number is 4521") >= 0.7


def test_entity_dense_message_scores_higher_than_plain():
    plain = score("the meeting went well today")
    entity_dense = score("Acme Corp and Beta Industries will merge with Gamma Holdings")
    assert entity_dense > plain


def test_score_capped_at_one():
    text = "Please remember this: I will commit to paying $5000 by Friday to Acme Corp Beta Gamma Delta"
    assert score(text) <= 1.0
