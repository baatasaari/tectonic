"""Request/response models for `/v1/conversational-engine/sessions` (LLD §3.3)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    channel: str
    persona_config_ref: str = "default"
    initial_context: dict = {}
    user_ref: str | None = None


class CreateSessionResponse(BaseModel):
    id: str
    status: str


class SendMessageRequest(BaseModel):
    content: str


class MessageSummary(BaseModel):
    id: str
    direction: str
    content: str
    emotion_score: float | None = None
    created_at: datetime


class TurnResponse(BaseModel):
    """Non-streaming turn response — the SSE path emits the same fields as
    a trailing `event: done` frame instead of a JSON body."""

    outbound_message: MessageSummary | None
    refused: bool
    refusal_category: str | None
    emotion_score: float
    handoff_triggered: bool


class SessionDetail(BaseModel):
    id: str
    tenant_id: str
    channel: str
    status: str
    persona_config_ref: str
    trace_id: str
    user_ref: str | None = None
    created_at: datetime
    last_activity_at: datetime
    messages: list[MessageSummary] = []


class SessionSummary(BaseModel):
    id: str
    tenant_id: str
    channel: str
    status: str
    persona_config_ref: str
    user_ref: str | None = None
    created_at: datetime
    last_activity_at: datetime


class SessionListResponse(BaseModel):
    items: list[SessionSummary]
    total: int
    limit: int
    offset: int


class HandoffEventSummary(BaseModel):
    id: str
    trigger_reason: str
    target: str
    created_at: datetime


class SessionExport(BaseModel):
    """Full transcript bundle for one session — the independent architecture
    assessment's Phase 2 exit bar ("session list/search/export/delete").
    Everything this module itself holds about the session in one document;
    it does not reach into Long-Term Memory or Auditability for their own
    records of it — see those modules' own export/evidence surfaces for
    that."""

    session: SessionDetail
    handoff_events: list[HandoffEventSummary] = []
    exported_at: datetime


class HandoffRequest(BaseModel):
    reason: str


class HandoffResponse(BaseModel):
    status: str
    handoff_event_id: str


class StatusResponse(BaseModel):
    status: str
