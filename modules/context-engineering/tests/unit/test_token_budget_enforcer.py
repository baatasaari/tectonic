from context_engineering.core.domain import CandidateItem, RankedItem, TaggedItem
from context_engineering.core.token_budget_enforcer import TokenBudgetEnforcer
from context_engineering.core.tokenization import SimpleTokenCounter


def _ranked(content: str, score: float) -> RankedItem:
    tagged = TaggedItem(candidate=CandidateItem(source="rag", content=content), role_match=False, entity_type_match=False)
    return RankedItem(tagged=tagged, priority_score=score)


def test_items_within_budget_all_fit():
    enforcer = TokenBudgetEnforcer(SimpleTokenCounter())
    items = [_ranked("short item one", 1.0), _ranked("short item two", 0.9)]
    selection = enforcer.select(items, token_budget=1000)
    assert len(selection.fits) == 2
    assert selection.overflow == []


def test_item_too_big_for_remaining_budget_overflows_but_later_smaller_item_still_fits():
    # The enforcer walks the already-priority-ranked list in order and is
    # greedy: an earlier item too big for the *remaining* budget overflows,
    # but it keeps trying later (lower-priority) items rather than stopping,
    # so budget isn't wasted just because the top-ranked item didn't fit.
    too_big = _ranked(" ".join(["word"] * 50), 1.0)
    fits_in_remainder = _ranked("tiny", 0.1)
    enforcer = TokenBudgetEnforcer(SimpleTokenCounter())

    selection = enforcer.select([too_big, fits_in_remainder], token_budget=20)

    assert [item for item, _ in selection.fits] == [fits_in_remainder]
    assert [item for item, _ in selection.overflow] == [too_big]


def test_tokens_used_matches_sum_of_fitted_items():
    enforcer = TokenBudgetEnforcer(SimpleTokenCounter())
    items = [_ranked("a b c", 1.0), _ranked("d e f g", 0.5)]
    selection = enforcer.select(items, token_budget=1000)
    expected = sum(t for _, t in selection.fits)
    assert selection.tokens_used == expected


def test_zero_budget_puts_everything_in_overflow():
    enforcer = TokenBudgetEnforcer(SimpleTokenCounter())
    items = [_ranked("anything at all", 1.0)]
    selection = enforcer.select(items, token_budget=0)
    assert selection.fits == []
    assert len(selection.overflow) == 1
