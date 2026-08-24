"""Framework-agnostic domain objects (LLD §3 data model)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class TaskDirection(StrEnum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class TaskStatus(StrEnum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input_required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


TERMINAL_STATUSES = frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELED})


class A2ATaskNotFoundError(Exception):
    def __init__(self, task_id: str) -> None:
        super().__init__(f"A2A task not found: {task_id}")


class AccessDeniedError(Exception):
    """Raised by the Access Policy Engine — deny-by-default: no policy row
    for (caller_agent_id, tenant_id) means zero access, and a skill outside
    the policy's allow-list is denied the same way. Same shape as MCP's own
    engine (Module 21), applied here to "per-skill, not just per-caller."
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class UnknownSkillError(Exception):
    """Raised when an inbound `message/send` names a skill this platform
    doesn't publish (not a key in `skill_definition_map`) — distinct from
    AccessDeniedError, since this isn't a policy decision, it's simply a
    skill that doesn't exist."""


class SkillNotAdvertisedError(Exception):
    """Raised by outbound delegation when the target agent's own Agent
    Card doesn't advertise the requested skill — failing fast locally
    instead of discovering the mismatch as an opaque error from the far
    side."""


@dataclass
class A2ATaskRecord:
    id: str
    tenant_id: str
    direction: TaskDirection
    peer_agent_url: str
    skill_id: str
    status: TaskStatus = TaskStatus.SUBMITTED
    input_message: dict[str, Any] = field(default_factory=dict)
    output_artifacts: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)


@dataclass
class A2AAccessPolicyRecord:
    id: str
    caller_agent_id: str
    tenant_id: str
    allowed_skills: list[str] | None = None  # None = every skill this platform publishes


@dataclass
class AgentCardCacheEntry:
    id: str
    agent_url: str
    card: dict[str, Any]
    fetched_at: datetime = field(default_factory=now)
    expires_at: datetime = field(default_factory=now)


@dataclass
class AgentSkill:
    id: str
    name: str
    description: str = ""


@dataclass
class AgentCard:
    name: str
    description: str
    url: str
    skills: list[AgentSkill] = field(default_factory=list)

    def supports(self, skill_id: str) -> bool:
        return any(s.id == skill_id for s in self.skills)


def parse_agent_card(raw: dict[str, Any]) -> AgentCard:
    """Tolerant parser for a fetched, third-party Agent Card: only pulls
    out the fields this module actually needs (name/description/url and
    each skill's id/name/description), ignoring any other fields a real
    A2A-spec card carries — this module isn't the trust-scored discovery
    registry (that's Module 23, Agent Cards), just a consumer doing a
    skill-match check before it sends."""
    skills = [
        AgentSkill(id=s.get("id", ""), name=s.get("name", ""), description=s.get("description", ""))
        for s in raw.get("skills", [])
    ]
    return AgentCard(name=raw.get("name", ""), description=raw.get("description", ""), url=raw.get("url", ""), skills=skills)


def card_to_dict(card: AgentCard) -> dict[str, Any]:
    return {
        "name": card.name,
        "description": card.description,
        "url": card.url,
        "skills": [{"id": s.id, "name": s.name, "description": s.description} for s in card.skills],
    }


@dataclass
class JsonRpcRequest:
    jsonrpc: str
    method: str
    params: dict[str, Any] | None
    id: str | int | None


@dataclass
class JsonRpcResponse:
    jsonrpc: str
    id: str | int | None
    result: Any | None = None
    error: dict[str, Any] | None = None
