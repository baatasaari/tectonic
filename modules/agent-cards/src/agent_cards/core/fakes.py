"""In-memory fakes for unit tests (LLD "Deployability and testability
contract")."""
from __future__ import annotations

from typing import Any

from agent_cards.core.domain import AgentCardRecord


class InMemoryAgentCardsRepository:
    def __init__(self) -> None:
        self.cards: dict[str, AgentCardRecord] = {}

    async def create_card(self, record: AgentCardRecord) -> AgentCardRecord:
        self.cards[record.id] = record
        return record

    async def get_card(self, card_id: str) -> AgentCardRecord | None:
        return self.cards.get(card_id)

    async def update_card(self, record: AgentCardRecord) -> AgentCardRecord:
        self.cards[record.id] = record
        return record

    async def list_cards(
        self, *, tenant_id: str | None = None, skill_id: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[AgentCardRecord], int]:
        results = list(self.cards.values())
        if tenant_id is not None:
            results = [c for c in results if c.tenant_id == tenant_id]
        if skill_id is not None:
            results = [c for c in results if any(s.id == skill_id for s in c.skills)]
        # trust_score descending, nulls last -- ties broken by created_at for stability.
        results = sorted(
            results, key=lambda c: (c.trust_score is None, -(c.trust_score or 0.0), c.created_at),
        )
        return results[offset:offset + limit], len(results)


class StubEvaluationFrameworkClient:
    def __init__(self, *, scores: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[dict] = []
        self._scores = scores if scores is not None else []

    async def list_scores(self, *, tenant_id: str, agent_ref: str) -> list[dict[str, Any]]:
        self.calls.append({"tenant_id": tenant_id, "agent_ref": agent_ref})
        return self._scores


class StubRegulatoryComplianceClient:
    def __init__(self, *, coverage_percentage: float | None = 100.0) -> None:
        self.calls: list[dict] = []
        self._coverage_percentage = coverage_percentage

    async def coverage(self, *, tenant_id: str, framework_name: str) -> float | None:
        self.calls.append({"tenant_id": tenant_id, "framework_name": framework_name})
        return self._coverage_percentage


__all__ = ["InMemoryAgentCardsRepository", "StubEvaluationFrameworkClient", "StubRegulatoryComplianceClient"]
