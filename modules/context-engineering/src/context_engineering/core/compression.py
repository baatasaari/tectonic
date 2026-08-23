"""Compression/Summarisation (LLD §2.2): for items that don't fit at full
length but are still high-priority, summarises rather than drops entirely.
Used sparingly given its own token cost — only called for overflow items,
never for anything that already fit.
"""
from __future__ import annotations

from dataclasses import dataclass

from context_engineering.core.domain import RankedItem
from context_engineering.core.ports import LLMGatewayClient
from context_engineering.core.tokenization import TokenCounter


@dataclass
class CompressionOutcome:
    item: RankedItem
    summary: str | None  # None if summarisation still didn't fit
    tokens: int


class CompressionService:
    def __init__(self, llm_gateway: LLMGatewayClient, token_counter: TokenCounter) -> None:
        self.llm_gateway = llm_gateway
        self.token_counter = token_counter

    async def summarise(self, item: RankedItem, remaining_budget: int, tenant_id: str) -> CompressionOutcome:
        if remaining_budget <= 0:
            return CompressionOutcome(item=item, summary=None, tokens=0)

        summary = await self.llm_gateway.summarise(
            content=item.tagged.candidate.content, target_tokens=remaining_budget, tenant_id=tenant_id
        )
        tokens = self.token_counter.count(summary)
        if tokens > remaining_budget:
            # The summariser overshot the target — truncate as a last
            # resort rather than dropping a high-priority item outright.
            summary = self.token_counter.truncate_to(summary, remaining_budget)
            tokens = self.token_counter.count(summary)
        if tokens > remaining_budget:
            return CompressionOutcome(item=item, summary=None, tokens=0)
        return CompressionOutcome(item=item, summary=summary, tokens=tokens)
