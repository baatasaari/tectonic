"""Framework-agnostic domain objects (LLD §3.1 data model). Mirrors Module
1's pattern: core logic works against these dataclasses, never SQLAlchemy
models directly, so it runs unchanged against the real repository or an
in-memory fake in unit tests.
"""
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


class SessionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    HANDED_OFF = "handed_off"
    CLOSED = "closed"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class Channel(StrEnum):
    WEB = "web"
    WHATSAPP = "whatsapp"
    VOICE = "voice"


class HandoffTriggerReason(StrEnum):
    EMOTION = "emotion"
    EXPLICIT = "explicit"
    REPEATED_REFUSAL = "repeated_refusal"


@dataclass
class PersonaConfigRecord:
    id: str
    tenant_id: str
    name: str
    tone_settings: dict[str, Any] = field(default_factory=dict)
    allowed_topics: list[str] = field(default_factory=list)
    denied_topics: list[str] = field(default_factory=list)


@dataclass
class ConversationSessionRecord:
    id: str
    tenant_id: str
    channel: Channel
    trace_id: str
    user_ref: str | None = None
    status: SessionStatus = SessionStatus.ACTIVE
    persona_config_ref: str = "default"
    created_at: datetime = field(default_factory=now)
    last_activity_at: datetime = field(default_factory=now)


@dataclass
class MessageRecord:
    id: str
    session_id: str
    direction: MessageDirection
    content: str
    emotion_score: float | None = None
    guardrail_check_result: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=now)


@dataclass
class HandoffEventRecord:
    id: str
    session_id: str
    trigger_reason: HandoffTriggerReason
    target: str  # "human" or an agent_id
    created_at: datetime = field(default_factory=now)


@dataclass
class TurnResult:
    """What handling one inbound message produced, for the API layer to
    render either as an SSE stream or a single JSON response."""

    outbound_message: MessageRecord | None
    refused: bool
    refusal_category: str | None
    emotion_score: float
    handoff_event: HandoffEventRecord | None
