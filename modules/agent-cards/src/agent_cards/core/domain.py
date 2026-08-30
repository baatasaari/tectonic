"""Framework-agnostic domain objects (LLD §3 data model)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class AgentCardNotFoundError(Exception):
    def __init__(self, card_id: str) -> None:
        super().__init__(f"Agent Card not found: {card_id}")


@dataclass
class AgentSkill:
    id: str
    name: str
    description: str = ""


@dataclass
class AgentCardRecord:
    id: str
    tenant_id: str
    agent_ref: str
    name: str
    description: str
    url: str
    skills: list[AgentSkill] = field(default_factory=list)
    trust_score: float | None = None
    trust_score_computed_at: datetime | None = None
    last_verified_at: datetime = field(default_factory=now)
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)

    def is_stale(self, *, ttl_seconds: int, at: datetime | None = None) -> bool:
        reference = at or now()
        age = (reference - self.last_verified_at).total_seconds()
        return age > ttl_seconds


@dataclass
class TrustScoreBreakdown:
    """The result of one trust-score computation -- kept separate from
    AgentCardRecord.trust_score (the persisted, current value) so a
    caller can see *how* a score was reached, not just the number.
    `performance_score`/`compliance_score` are `None` when that signal's
    upstream peer had no data yet -- not zero, which would look like a
    real, bad score rather than "unknown".
    """

    performance_score: float | None
    compliance_score: float | None
    trust_score: float | None
    computed_at: datetime = field(default_factory=now)

    @property
    def insufficient_data(self) -> bool:
        return self.performance_score is None and self.compliance_score is None


def skills_to_dicts(skills: list[AgentSkill]) -> list[dict[str, Any]]:
    return [{"id": s.id, "name": s.name, "description": s.description} for s in skills]


def skills_from_dicts(raw: list[dict[str, Any]]) -> list[AgentSkill]:
    return [AgentSkill(id=s.get("id", ""), name=s.get("name", ""), description=s.get("description", "")) for s in raw]
