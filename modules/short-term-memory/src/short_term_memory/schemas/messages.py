"""Request/response models for `/v1/short-term-memory/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AppendMessageRequest(BaseModel):
    content: str
    role: str


class MessageSchema(BaseModel):
    content: str
    role: str
    token_count: int
    salience_score: float
    timestamp: datetime


class BufferStateSchema(BaseModel):
    session_id: str
    messages: list[MessageSchema]
    summary: str | None
    token_count: int


class AppendResponse(BaseModel):
    token_count: int
    overflow_triggered: bool


class DeleteResponse(BaseModel):
    status: str
