"""Abstract ports the execution engine depends on.

Everything the scheduler/executors touch outside their own logic — persistence,
event publishing, and the four external module dependencies (LLM Gateway, Tool
Orchestration, Guardrails, Human Oversight) — is expressed as a Protocol here.
Production wires the real adapters (SQLAlchemy repository, aiokafka publisher,
HTTP clients); unit tests wire in-memory fakes/stubs. This is what lets this
module be developed and tested fully stubbed, per the LLD's Deployability and
Testability Contract (§ Level 1).
"""
from __future__ import annotations

from typing import Any, Protocol

from workflow_engine.core.domain import (
    ApprovalRequestRecord,
    EventOutboxRecord,
    ReplanEventRecord,
    StepExecutionRecord,
    WorkflowDefinitionRecord,
    WorkflowInstanceRecord,
)


class WorkflowRepository(Protocol):
    async def get_definition(self, definition_id: str) -> WorkflowDefinitionRecord | None: ...

    async def create_definition(self, record: WorkflowDefinitionRecord) -> WorkflowDefinitionRecord: ...

    async def publish_definition(self, definition_id: str) -> WorkflowDefinitionRecord: ...

    async def create_instance(self, record: WorkflowInstanceRecord) -> WorkflowInstanceRecord: ...

    async def get_instance(self, instance_id: str) -> WorkflowInstanceRecord | None: ...

    async def update_instance(self, record: WorkflowInstanceRecord) -> WorkflowInstanceRecord: ...

    async def update_instance_and_enqueue_event(
        self, record: WorkflowInstanceRecord, *, topic: str, envelope: dict[str, Any],
    ) -> WorkflowInstanceRecord:
        """Atomically updates the instance AND enqueues its accompanying
        CloudEvents envelope into `event_outbox`, one DB commit -- see
        `EventOutboxRecord`'s own docstring for why this, not
        `update_instance` + a separate direct publish, is what backs
        the three top-level instance-lifecycle events."""
        ...

    async def create_step_execution(self, record: StepExecutionRecord) -> StepExecutionRecord: ...

    async def update_step_execution(self, record: StepExecutionRecord) -> StepExecutionRecord: ...

    async def list_step_executions(
        self, instance_id: str, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[StepExecutionRecord], int]: ...

    async def get_step_execution(self, step_execution_id: str) -> StepExecutionRecord | None: ...

    async def create_approval_request(self, record: ApprovalRequestRecord) -> ApprovalRequestRecord: ...

    async def get_approval_request(self, approval_id: str) -> ApprovalRequestRecord | None: ...

    async def update_approval_request(self, record: ApprovalRequestRecord) -> ApprovalRequestRecord: ...

    async def create_replan_event(self, record: ReplanEventRecord) -> ReplanEventRecord: ...

    # --- Event outbox relay (core/outbox_worker.py) ---

    async def claim_next_outbox_event(self, worker_id: str, lease_seconds: int) -> EventOutboxRecord | None:
        """`SELECT ... FOR UPDATE SKIP LOCKED` in the SQL implementation --
        the same claim shape `claim_next_evidence_pack` (Regulatory
        Compliance) already established for this platform's durable
        background jobs, so multiple worker processes/pods can poll
        this table concurrently with no double-claim."""
        ...

    async def mark_outbox_event_published(self, event_id: str) -> None: ...

    async def requeue_outbox_event_for_retry(self, event_id: str, *, error: str) -> None: ...

    async def fail_exhausted_outbox_events(self, max_attempts: int) -> int:
        """The poison-pill guard: an event that has failed `max_attempts`
        times in a row stops being retried and is marked `failed` for
        good, rather than being reclaimed forever."""
        ...

    async def force_expire_stale_outbox_leases(self) -> int:
        """The startup recovery sweep: force-expires every currently-held
        lease, so anything left mid-flight by a now-dead previous worker
        instance is reclaimed on the very next poll tick."""
        ...


class EventPublisher(Protocol):
    async def publish(self, topic: str, event: dict[str, Any]) -> None: ...


class LLMGatewayClient(Protocol):
    """Port to the LLM Gateway module (Module 3). Never call a model provider directly."""

    async def complete(
        self, *, agent_ref: str, prompt_context: dict[str, Any], tenant_id: str, trace_id: str
    ) -> tuple[dict[str, Any], float]:
        """Returns (response, confidence_score)."""
        ...


class ToolOrchestrationClient(Protocol):
    async def invoke(
        self, *, tool_ref: str, arguments: dict[str, Any], tenant_id: str, trace_id: str
    ) -> dict[str, Any]: ...


class GuardrailsClient(Protocol):
    async def check(
        self, *, content: dict[str, Any], policy_profile: str, tenant_id: str
    ) -> tuple[bool, dict[str, Any]]:
        """Returns (allowed, decision_detail)."""
        ...


class HumanOversightClient(Protocol):
    async def request_approval(
        self, *, approval_request_id: str, step_execution_id: str, context: dict[str, Any], tenant_id: str
    ) -> str:
        """Registers the request with Human Oversight, returns its external ref id."""
        ...
