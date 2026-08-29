"""In-memory fakes for the ports in core/ports.py — the unit-test tier and
local dev without Redis/Postgres/dependency modules, mirroring Module 1's
core/fakes.py.
"""
from __future__ import annotations

import copy
from collections.abc import AsyncIterator
from typing import Any

from conversational_engine.core.domain import (
    ConversationSessionRecord,
    HandoffEventRecord,
    MessageRecord,
    PersonaConfigRecord,
)


class InMemoryConversationRepository:
    def __init__(self) -> None:
        self.sessions: dict[str, ConversationSessionRecord] = {}
        self.messages: dict[str, list[MessageRecord]] = {}
        self.handoff_events: list[HandoffEventRecord] = []
        self.personas: dict[tuple[str, str], PersonaConfigRecord] = {}

    def seed_persona(self, persona: PersonaConfigRecord) -> None:
        self.personas[(persona.tenant_id, persona.id)] = persona

    async def create_session(self, record: ConversationSessionRecord) -> ConversationSessionRecord:
        self.sessions[record.id] = copy.deepcopy(record)
        self.messages.setdefault(record.id, [])
        return copy.deepcopy(record)

    async def get_session(self, session_id: str) -> ConversationSessionRecord | None:
        rec = self.sessions.get(session_id)
        return copy.deepcopy(rec) if rec else None

    async def update_session(self, record: ConversationSessionRecord) -> ConversationSessionRecord:
        self.sessions[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def append_message(self, record: MessageRecord) -> MessageRecord:
        self.messages.setdefault(record.session_id, []).append(copy.deepcopy(record))
        return copy.deepcopy(record)

    async def list_messages(self, session_id: str) -> list[MessageRecord]:
        return [copy.deepcopy(m) for m in self.messages.get(session_id, [])]

    async def create_handoff_event(self, record: HandoffEventRecord) -> HandoffEventRecord:
        self.handoff_events.append(copy.deepcopy(record))
        return copy.deepcopy(record)

    async def get_latest_handoff_event(self, session_id: str) -> HandoffEventRecord | None:
        matches = [e for e in self.handoff_events if e.session_id == session_id]
        return copy.deepcopy(matches[-1]) if matches else None

    async def get_persona_config(self, persona_config_ref: str, tenant_id: str) -> PersonaConfigRecord | None:
        rec = self.personas.get((tenant_id, persona_config_ref)) or self.personas.get(("*", persona_config_ref))
        return copy.deepcopy(rec) if rec else None


class InMemorySessionStateStore:
    def __init__(self) -> None:
        self._state: dict[str, dict[str, Any]] = {}

    async def get(self, session_id: str) -> dict[str, Any] | None:
        rec = self._state.get(session_id)
        return copy.deepcopy(rec) if rec else None

    async def set(self, session_id: str, state: dict[str, Any], ttl_seconds: int) -> None:
        self._state[session_id] = copy.deepcopy(state)

    async def delete(self, session_id: str) -> None:
        self._state.pop(session_id, None)


class StubLLMGatewayClient:
    """Deterministic stand-in for the LLM Gateway module (Module 3)."""

    def __init__(self, response_chunks: list[str] | None = None) -> None:
        self.default_chunks = response_chunks or ["Sure, ", "here's ", "an answer."]
        self.classify_result: dict[str, float] = {"calm": 1.0, "frustrated": 0.0, "urgent": 0.0}
        self.calls: list[dict[str, Any]] = []

    async def stream_complete(
        self, *, prompt_context: dict[str, Any], tenant_id: str, trace_id: str
    ) -> AsyncIterator[str]:
        self.calls.append({"prompt_context": prompt_context, "tenant_id": tenant_id})
        for chunk in self.default_chunks:
            yield chunk

    async def classify(self, *, text: str, taxonomy: list[str], tenant_id: str) -> dict[str, float]:
        return dict(self.classify_result)


class StubWorkflowEngineClient:
    """Deterministic stand-in for the Workflow Engine module (Module 1),
    added for the WorkflowEngineClient port (ticket #82)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses: list[dict[str, Any]] = []
        self.instance_responses: dict[str, dict[str, Any]] = {}
        self.default_response: dict[str, Any] = {
            "id": "instance-1", "status": "completed", "trace_id": "trace-1",
            "context": {"respond": {"content": "stub workflow response"}},
        }

    def queue_response(self, response: dict[str, Any]) -> None:
        self._responses.append(response)

    def queue_instance_response(self, instance_id: str, response: dict[str, Any]) -> None:
        """Sets what a later `get_instance(instance_id=...)` call returns --
        for a test to simulate Human Oversight's own decision-callback
        having resumed a paused instance to completion (ticket #82)."""
        self.instance_responses[instance_id] = response

    async def start_instance(
        self, *, definition_id: str, initial_context: dict[str, Any], tenant_id: str
    ) -> dict[str, Any]:
        self.calls.append({"definition_id": definition_id, "initial_context": initial_context, "tenant_id": tenant_id})
        if self._responses:
            return self._responses.pop(0)
        return copy.deepcopy(self.default_response)

    async def get_instance(self, *, instance_id: str, tenant_id: str) -> dict[str, Any]:
        if instance_id in self.instance_responses:
            return copy.deepcopy(self.instance_responses[instance_id])
        return copy.deepcopy(self.default_response)


class StubGuardrailsClient:
    def __init__(self) -> None:
        self.block_next = False
        self.violation_category = "policy_violation"

    async def check(
        self, *, content: dict[str, Any], policy_profile: str, tenant_id: str
    ) -> tuple[bool, dict[str, Any]]:
        if self.block_next:
            return False, {"violation_category": self.violation_category, "detail": "blocked-for-test"}
        return True, {"policy_profile": policy_profile, "violations": []}


class StubLongTermMemoryClient:
    async def recall_identity_context(self, *, user_ref: str, tenant_id: str) -> dict[str, Any] | None:
        return None


class StubHumanOversightClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    async def request_handoff(
        self, *, session_id: str, trigger_reason: str, context: dict[str, Any], tenant_id: str
    ) -> str:
        self.requests.append(
            {"session_id": session_id, "trigger_reason": trigger_reason, "context": context, "tenant_id": tenant_id}
        )
        return f"ho-ref-{session_id}"


class InMemoryObservabilityClient:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(self, event: dict[str, Any]) -> None:
        self.events.append(copy.deepcopy(event))


class InMemoryAuditabilityClient:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(self, event: dict[str, Any]) -> None:
        self.events.append(copy.deepcopy(event))
