"""In-memory fakes for the ports in core/ports.py — the unit-test tier,
mirroring the other modules' core/fakes.py.
"""
from __future__ import annotations

import copy

from short_term_memory.core.domain import BufferState


class InMemoryBufferStore:
    def __init__(self) -> None:
        self.states: dict[str, BufferState] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, session_id: str) -> BufferState | None:
        state = self.states.get(session_id)
        return copy.deepcopy(state) if state else None

    async def save(self, session_id: str, state: BufferState, ttl_seconds: int) -> None:
        self.states[session_id] = copy.deepcopy(state)
        self.ttls[session_id] = ttl_seconds

    async def delete(self, session_id: str) -> None:
        self.states.pop(session_id, None)
        self.ttls.pop(session_id, None)


class StubLLMGatewayClient:
    def __init__(self) -> None:
        self.canned_summary: str | None = None
        self.calls: list[dict] = []

    async def summarise(self, text: str, tenant_id: str) -> str:
        self.calls.append({"text": text, "tenant_id": tenant_id})
        if self.canned_summary is not None:
            return self.canned_summary
        return f"Summary of {len(text.splitlines())} message(s)."
