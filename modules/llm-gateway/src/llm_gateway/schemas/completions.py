"""OpenAI-compatible request/response models (LLD §3.3)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChatMessageSchema(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessageSchema]
    routing_hints: dict[str, Any] = {}


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessageSchema
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible body; provider/cache/cost metadata also rides on
    `x-provider-used` / `x-cache-hit` / `x-cost` response headers per the
    LLD, and is duplicated into the body here for non-header-reading clients."""

    id: str
    object: str = "chat.completion"
    model: str
    choices: list[ChatCompletionChoice]
    provider_used: str
    cache_hit: bool
    cost: float
    usage: dict[str, int]


class EmbeddingsRequest(BaseModel):
    model: str
    input: str


class EmbeddingsResponse(BaseModel):
    object: str = "list"
    model: str
    data: list[dict[str, Any]]
    provider_used: str
