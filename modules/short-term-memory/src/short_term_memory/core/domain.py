"""Framework-agnostic domain objects (LLD §3 "Data model (Redis
structures, not relational)")."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)


@dataclass
class MessageRecord:
    content: str
    role: str
    token_count: int
    salience_score: float
    timestamp: datetime = field(default_factory=now)


@dataclass
class BufferState:
    session_id: str
    messages: list[MessageRecord] = field(default_factory=list)
    summary: str | None = None
    token_count: int = 0


@dataclass
class AppendResult:
    state: BufferState
    overflow_triggered: bool
