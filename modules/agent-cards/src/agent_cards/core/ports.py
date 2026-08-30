"""Abstract ports this module depends on: persistence, and the two real
platform-peer clients the Trust Score Calculator reads from.
"""
from __future__ import annotations

from typing import Any, Protocol

from agent_cards.core.domain import AgentCardRecord


class AgentCardsRepository(Protocol):
    async def create_card(self, record: AgentCardRecord) -> AgentCardRecord: ...

    async def get_card(self, card_id: str) -> AgentCardRecord | None: ...

    async def update_card(self, record: AgentCardRecord) -> AgentCardRecord: ...

    async def list_cards(
        self, *, tenant_id: str | None = None, skill_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[AgentCardRecord], int]:
        """Sorted by trust_score descending (nulls last) -- the LLD's own
        "ranks by trust score, not registration order" differentiator."""
        ...


class EvaluationFrameworkClient(Protocol):
    async def list_scores(self, *, tenant_id: str, agent_ref: str) -> list[dict[str, Any]]:
        """Each item at least `{"score": float, "threshold": float}`, per
        Evaluation Framework's own MetricScoreSchema. Empty list, not an
        error, when the agent has no evaluation history yet."""
        ...


class RegulatoryComplianceClient(Protocol):
    async def coverage(self, *, tenant_id: str, framework_name: str) -> float | None:
        """Returns `coverage_percentage` (0-100), or None if the tenant
        has no coverage computed yet for that framework."""
        ...
