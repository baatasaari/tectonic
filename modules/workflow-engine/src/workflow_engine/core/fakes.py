"""In-memory fakes for the ports in core/ports.py.

Used by the unit test tier (LLD §4.8: "unit tests use in-memory fakes only")
and by local `make dev` runs where the full dependency stack isn't up.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import timedelta
from typing import Any

from workflow_engine.core.domain import (
    ApprovalRequestRecord,
    EventOutboxRecord,
    OutboxEventStatus,
    ReplanEventRecord,
    StepExecutionRecord,
    WorkflowDefinitionRecord,
    WorkflowInstanceRecord,
    now,
)


class InMemoryWorkflowRepository:
    def __init__(self) -> None:
        self.definitions: dict[str, WorkflowDefinitionRecord] = {}
        self.instances: dict[str, WorkflowInstanceRecord] = {}
        self.steps: dict[str, StepExecutionRecord] = {}
        self.approvals: dict[str, ApprovalRequestRecord] = {}
        self.replan_events: list[ReplanEventRecord] = []
        self.outbox: dict[str, EventOutboxRecord] = {}

    async def get_definition(self, definition_id: str) -> WorkflowDefinitionRecord | None:
        rec = self.definitions.get(definition_id)
        return copy.deepcopy(rec) if rec else None

    async def create_definition(self, record: WorkflowDefinitionRecord) -> WorkflowDefinitionRecord:
        self.definitions[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def publish_definition(self, definition_id: str) -> WorkflowDefinitionRecord:
        from workflow_engine.core.domain import DefinitionStatus, now

        rec = self.definitions[definition_id]
        rec = replace(rec, status=DefinitionStatus.PUBLISHED, published_at=now())
        self.definitions[definition_id] = rec
        return copy.deepcopy(rec)

    async def create_instance(self, record: WorkflowInstanceRecord) -> WorkflowInstanceRecord:
        self.instances[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_instance(self, instance_id: str) -> WorkflowInstanceRecord | None:
        rec = self.instances.get(instance_id)
        return copy.deepcopy(rec) if rec else None

    async def update_instance(self, record: WorkflowInstanceRecord) -> WorkflowInstanceRecord:
        self.instances[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def create_step_execution(self, record: StepExecutionRecord) -> StepExecutionRecord:
        self.steps[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def update_step_execution(self, record: StepExecutionRecord) -> StepExecutionRecord:
        self.steps[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def list_step_executions(
        self, instance_id: str, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[StepExecutionRecord], int]:
        results = [s for s in self.steps.values() if s.instance_id == instance_id]
        # id ascending, matching the SQL repository's ORDER BY id (no non-nullable timestamp
        # column exists on StepExecution to order by instead).
        results = sorted(results, key=lambda s: s.id)
        return [copy.deepcopy(s) for s in results[offset:offset + limit]], len(results)

    async def get_step_execution(self, step_execution_id: str) -> StepExecutionRecord | None:
        rec = self.steps.get(step_execution_id)
        return copy.deepcopy(rec) if rec else None

    async def create_approval_request(self, record: ApprovalRequestRecord) -> ApprovalRequestRecord:
        self.approvals[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_approval_request(self, approval_id: str) -> ApprovalRequestRecord | None:
        rec = self.approvals.get(approval_id)
        return copy.deepcopy(rec) if rec else None

    async def update_approval_request(self, record: ApprovalRequestRecord) -> ApprovalRequestRecord:
        self.approvals[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def create_replan_event(self, record: ReplanEventRecord) -> ReplanEventRecord:
        self.replan_events.append(copy.deepcopy(record))
        return copy.deepcopy(record)

    async def update_instance_and_enqueue_event(
        self, record: WorkflowInstanceRecord, *, topic: str, envelope: dict[str, Any],
    ) -> WorkflowInstanceRecord:
        self.instances[record.id] = copy.deepcopy(record)
        outbox_record = EventOutboxRecord(
            id=envelope["id"], topic=topic, tenant_id=envelope["tenant_id"], envelope=copy.deepcopy(envelope),
        )
        self.outbox[outbox_record.id] = outbox_record
        return copy.deepcopy(record)

    async def claim_next_outbox_event(self, worker_id: str, lease_seconds: int) -> EventOutboxRecord | None:
        moment = now()
        candidates = [
            e for e in self.outbox.values()
            if e.status == OutboxEventStatus.PENDING and (e.lease_expires_at is None or e.lease_expires_at < moment)
        ]
        if not candidates:
            return None
        oldest = min(candidates, key=lambda e: e.created_at)
        oldest.worker_id = worker_id
        oldest.attempts += 1
        oldest.lease_expires_at = moment + timedelta(seconds=lease_seconds)
        return copy.deepcopy(oldest)

    async def mark_outbox_event_published(self, event_id: str) -> None:
        record = self.outbox.get(event_id)
        if record is None:
            return
        record.status = OutboxEventStatus.PUBLISHED
        record.published_at = now()
        record.lease_expires_at = None

    async def requeue_outbox_event_for_retry(self, event_id: str, *, error: str) -> None:
        record = self.outbox.get(event_id)
        if record is None:
            return
        record.lease_expires_at = None
        record.last_error = error

    async def fail_exhausted_outbox_events(self, max_attempts: int) -> int:
        count = 0
        for record in self.outbox.values():
            if record.status == OutboxEventStatus.PENDING and record.attempts >= max_attempts:
                record.status = OutboxEventStatus.FAILED
                record.last_error = f"exceeded max attempts ({max_attempts})"
                count += 1
        return count

    async def force_expire_stale_outbox_leases(self) -> int:
        moment = now()
        count = 0
        for record in self.outbox.values():
            if (
                record.status == OutboxEventStatus.PENDING
                and record.lease_expires_at is not None
                and record.lease_expires_at > moment
            ):
                record.lease_expires_at = moment
                count += 1
        return count


class InMemoryEventPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        self.published.append((topic, copy.deepcopy(event)))


class StubLLMGatewayClient:
    """Deterministic stand-in for the LLM Gateway module (Module 3).

    Returns a fixed confidence unless the caller pre-seeds a response via
    `set_response`, which tests use to exercise both branches of the
    confidence-gate.
    """

    def __init__(self, default_confidence: float = 0.95) -> None:
        self.default_confidence = default_confidence
        self._overrides: dict[str, tuple[dict[str, Any], float]] = {}
        self.calls: list[dict[str, Any]] = []

    def set_response(self, agent_ref: str, response: dict[str, Any], confidence: float) -> None:
        self._overrides[agent_ref] = (response, confidence)

    async def complete(
        self, *, agent_ref: str, prompt_context: dict[str, Any], tenant_id: str, trace_id: str
    ) -> tuple[dict[str, Any], float]:
        self.calls.append({"agent_ref": agent_ref, "prompt_context": prompt_context, "tenant_id": tenant_id})
        if agent_ref in self._overrides:
            return self._overrides[agent_ref]
        return {"content": f"stub completion for {agent_ref}"}, self.default_confidence


class StubToolOrchestrationClient:
    async def invoke(
        self, *, tool_ref: str, arguments: dict[str, Any], tenant_id: str, trace_id: str
    ) -> dict[str, Any]:
        return {"tool_ref": tool_ref, "result": "stub-ok", "arguments": arguments}


class StubGuardrailsClient:
    async def check(
        self, *, content: dict[str, Any], policy_profile: str, tenant_id: str
    ) -> tuple[bool, dict[str, Any]]:
        return True, {"policy_profile": policy_profile, "violations": []}


class StubHumanOversightClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    async def request_approval(
        self, *, approval_request_id: str, step_execution_id: str, context: dict[str, Any], tenant_id: str
    ) -> str:
        self.requests.append(
            {
                "approval_request_id": approval_request_id,
                "step_execution_id": step_execution_id,
                "context": context,
                "tenant_id": tenant_id,
            }
        )
        return f"ho-ref-{approval_request_id}"
