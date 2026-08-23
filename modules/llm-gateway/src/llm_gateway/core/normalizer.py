"""Request Normalizer (LLD §2.2): converts an OpenAI-compatible caller
request into the gateway's internal canonical form.
"""
from __future__ import annotations

from llm_gateway.core.domain import ChatMessage, CompletionRequest


class NormalizationError(Exception):
    pass


def normalize_chat_request(
    raw: dict, *, tenant_id: str, virtual_key_id: str
) -> CompletionRequest:
    model = raw.get("model")
    if not model:
        raise NormalizationError("'model' is required")

    raw_messages = raw.get("messages")
    if not raw_messages:
        raise NormalizationError("'messages' is required and must be non-empty")

    messages = []
    for m in raw_messages:
        if "role" not in m or "content" not in m:
            raise NormalizationError("each message requires 'role' and 'content'")
        messages.append(ChatMessage(role=m["role"], content=m["content"]))

    routing_hints = raw.get("routing_hints", {})
    task_type = routing_hints.get("task_type", "chat")

    return CompletionRequest(
        model=model,
        messages=messages,
        tenant_id=tenant_id,
        virtual_key_id=virtual_key_id,
        routing_hints=routing_hints,
        task_type=task_type,
    )
