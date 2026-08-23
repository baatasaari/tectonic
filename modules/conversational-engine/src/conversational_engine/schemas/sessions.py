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
    created_at: datetime
    last_activity_at: datetime
    messages: list[MessageSummary] = []


class HandoffRequest(BaseModel):
    reason: str


class HandoffResponse(BaseModel):
    status: str
    handoff_event_id: str


class StatusResponse(BaseModel):
    status: str
