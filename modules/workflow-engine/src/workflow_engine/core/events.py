"""Event topic names and payload builders for the async lifecycle events
this module emits (LLD §2.2 Event Bus Publisher, §3.4/§3.5 sequence
diagrams). Consumed downstream by Observability, Auditability and the
Evaluation Framework.
"""
from __future__ import annotations

from typing import Any

from workflow_engine.core.domain import now

TOPIC_WORKFLOW_INSTANCE = "workflow.instance"
TOPIC_WORKFLOW_STEP = "workflow.step"
TOPIC_WORKFLOW_REPLAN = "workflow.replan"
TOPIC_WORKFLOW_APPROVAL = "workflow.approval"


def _event(event_type: str, tenant_id: str, trace_id: str, **fields: Any) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "tenant_id": tenant_id,
        "trace_id": trace_id,
        "emitted_at": now().isoformat(),
        **fields,
    }


def workflow_started(tenant_id: str, trace_id: str, instance_id: str, definition_id: str) -> dict[str, Any]:
    return _event("workflow.started", tenant_id, trace_id, instance_id=instance_id, definition_id=definition_id)


def workflow_completed(tenant_id: str, trace_id: str, instance_id: str) -> dict[str, Any]:
    return _event("workflow.completed", tenant_id, trace_id, instance_id=instance_id)


def workflow_failed(tenant_id: str, trace_id: str, instance_id: str, reason: str) -> dict[str, Any]:
    return _event("workflow.failed", tenant_id, trace_id, instance_id=instance_id, reason=reason)


def workflow_paused_for_approval(tenant_id: str, trace_id: str, instance_id: str, step_id: str) -> dict[str, Any]:
    return _event(
        "workflow.paused_for_approval", tenant_id, trace_id, instance_id=instance_id, step_id=step_id
    )


def step_started(tenant_id: str, trace_id: str, instance_id: str, step_id: str, execution_mode: str) -> dict[str, Any]:
    return _event(
        "step.started",
        tenant_id,
        trace_id,
        instance_id=instance_id,
        step_id=step_id,
        execution_mode=execution_mode,
    )


def step_completed(
    tenant_id: str,
    trace_id: str,
    instance_id: str,
    step_id: str,
    execution_mode: str,
    confidence_score: float | None,
) -> dict[str, Any]:
    return _event(
        "step.completed",
        tenant_id,
        trace_id,
        instance_id=instance_id,
        step_id=step_id,
        execution_mode=execution_mode,
        confidence_score=confidence_score,
    )


def step_failed(
    tenant_id: str, trace_id: str, instance_id: str, step_id: str, retry_count: int, error: str
) -> dict[str, Any]:
    return _event(
        "step.failed",
        tenant_id,
        trace_id,
        instance_id=instance_id,
        step_id=step_id,
        retry_count=retry_count,
        error=error,
    )


def approval_requested(
    tenant_id: str, trace_id: str, instance_id: str, step_id: str, approval_request_id: str, timeout_seconds: int
) -> dict[str, Any]:
    return _event(
        "approval.requested",
        tenant_id,
        trace_id,
        instance_id=instance_id,
        step_id=step_id,
        approval_request_id=approval_request_id,
        timeout_seconds=timeout_seconds,
    )


def approval_resolved(
    tenant_id: str, trace_id: str, instance_id: str, step_id: str, approval_request_id: str, decision: str
) -> dict[str, Any]:
    return _event(
        "approval.resolved",
        tenant_id,
        trace_id,
        instance_id=instance_id,
        step_id=step_id,
        approval_request_id=approval_request_id,
        decision=decision,
    )


def replan_triggered(
    tenant_id: str, trace_id: str, instance_id: str, original_step_id: str, reason: str, outcome: str
) -> dict[str, Any]:
    return _event(
        "replan.triggered",
        tenant_id,
        trace_id,
        instance_id=instance_id,
        original_step_id=original_step_id,
        reason=reason,
        outcome=outcome,
    )
