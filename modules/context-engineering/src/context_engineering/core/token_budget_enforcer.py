"""Token Budget Enforcer (LLD §2.2): selects the highest-priority items
that fit within the token budget — greedy knapsack-style selection against
token counts, walking the already-priority-ranked list in order.
"""
from __future__ import annotations

from dataclasses import dataclass

from context_engineering.core.domain import RankedItem
from context_engineering.core.tokenization import TokenCounter


@dataclass
class BudgetSelection:
    fits: list[tuple[RankedItem, int]]  # (item, token_count)
    overflow: list[tuple[RankedItem, int]]
    tokens_used: int


class TokenBudgetEnforcer:
    def __init__(self, token_counter: TokenCounter) -> None:
        self.token_counter = token_counter

    def select(self, ranked_items: list[RankedItem], token_budget: int) -> BudgetSelection:
        fits: list[tuple[RankedItem, int]] = []
        overflow: list[tuple[RankedItem, int]] = []
        remaining = token_budget

        for item in ranked_items:
            tokens = self.token_counter.count(item.tagged.candidate.content)
            if tokens <= remaining:
                fits.append((item, tokens))
                remaining -= tokens
            else:
                overflow.append((item, tokens))

        return BudgetSelection(fits=fits, overflow=overflow, tokens_used=token_budget - remaining)
