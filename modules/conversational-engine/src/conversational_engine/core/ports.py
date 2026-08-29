"""Abstract ports the Session Manager depends on: persistence, hot session
state, and the module's external dependencies (LLM Gateway, Guardrails,
Long-Term Memory, Human Oversight, Observability, Auditability). Production
wires real adapters; unit tests wire in-memory fakes — same testability
contract as Module 1.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from conversational_engine.core.domain import (
    ConversationSessionRecord,
    HandoffEventRecord,
    MessageRecord,
    PersonaConfigRecord,
)


class ConversationRepository(Protocol):
    async def create_session(self, record: ConversationSessionRecord) -> ConversationSessionRecord: ...

    async def get_session(self, session_id: str) -> ConversationSessionRecord | None: ...

    async def update_session(self, record: ConversationSessionRecord) -> ConversationSessionRecord: ...

    async def append_message(self, record: MessageRecord) -> MessageRecord: ...

    async def list_messages(self, session_id: str) -> list[MessageRecord]: ...

    async def create_handoff_event(self, record: HandoffEventRecord) -> HandoffEventRecord: ...

    async def get_persona_config(self, persona_config_ref: str, tenant_id: str) -> PersonaConfigRecord | None: ...


class SessionStateStore(Protocol):
    """Hot session state (Redis in production) — hand-off-ready turn context
    that doesn't need Postgres's durability, keyed with a TTL per LLD §4.5."""

    async def get(self, session_id: str) -> dict[str, Any] | None: ...

    async def set(self, session_id: str, state: dict[str, Any], ttl_seconds: int) -> None: ...

    async def delete(self, session_id: str) -> None: ...


class LLMGatewayClient(Protocol):
    """Port to the LLM Gateway module (Module 3)."""

    def stream_complete(
        self, *, prompt_context: dict[str, Any], tenant_id: str, trace_id: str
    ) -> AsyncIterator[str]:
        """Yields response text chunks as they're generated."""
        ...

    async def classify(
        self, *, text: str, taxonomy: list[str], tenant_id: str
    ) -> dict[str, float]:
        """Small-model classification call, used as the LLM-backed emotion/
        urgency signal when the heuristic scorer is inconclusive."""
        ...


class GuardrailsClient(Protocol):
    async def check(
        self, *, content: dict[str, Any], policy_profile: str, tenant_id: str
    ) -> tuple[bool, dict[str, Any]]:
        """Returns (allowed, decision_detail). decision_detail carries a
        `violation_category` when not allowed, for the Refusal Composer."""
        ...


class LongTermMemoryClient(Protocol):
    async def recall_identity_context(self, *, user_ref: str, tenant_id: str) -> dict[str, Any] | None: ...


class HumanOversightClient(Protocol):
    async def request_handoff(
        self, *, session_id: str, trigger_reason: str, context: dict[str, Any], tenant_id: str
    ) -> str:
        """Returns an external handoff ticket/ref id."""
        ...


class WorkflowEngineClient(Protocol):
    """Port to the Workflow Engine module (Module 1). Added for the Phase 2
    support-agent product slice (ticket #82): this module had no client for
    Workflow Engine at all before this -- handle_turn() called LLM Gateway
    directly for every turn, never routing through Workflow Engine's own
    neurosymbolic orchestration, contrary to what the slice's own design doc
    always assumed. Gated behind `settings.workflow_routing.enabled` (default
    off) so every pre-existing direct-LLM-Gateway turn is unaffected."""

    async def start_instance(
        self, *, definition_id: str, initial_context: dict[str, Any], tenant_id: str
    ) -> dict[str, Any]:
        """POSTs /instances; Workflow Engine runs the graph synchronously
        within the call. Returns {"id", "status", "trace_id", "context"} --
        status is "completed" (context carries the final answer),
        "paused_for_approval" (escalated to Human Oversight), or "failed"."""
        ...


class ObservabilityClient(Protocol):
    async def emit(self, event: dict[str, Any]) -> None: ...


class AuditabilityClient(Protocol):
    async def emit(self, event: dict[str, Any]) -> None: ...
