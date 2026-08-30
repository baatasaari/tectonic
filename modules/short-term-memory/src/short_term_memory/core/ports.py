"""Abstract ports the Buffer Manager depends on: session-state persistence
and the LLM Gateway summarisation dependency.
"""
from __future__ import annotations

from typing import Protocol

from short_term_memory.core.domain import BufferState


class BufferStore(Protocol):
    async def get(self, session_id: str) -> BufferState | None: ...

    async def save(self, session_id: str, state: BufferState, ttl_seconds: int) -> None: ...

    async def delete(self, session_id: str) -> None: ...


class LLMGatewayClient(Protocol):
    async def summarise(self, text: str, tenant_id: str) -> str: ...
