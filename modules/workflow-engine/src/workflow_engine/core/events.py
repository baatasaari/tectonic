"""Event topic names and CloudEvents-shaped envelope builders for the
async lifecycle events this module emits (LLD §2.2 Event Bus Publisher,
§3.4/§3.5 sequence diagrams; independent architecture assessment §3.3
"Add an event backbone"). Consumed downstream by Observability,
Auditability and the Evaluation Framework once those modules add a real
Kafka consumer -- none does yet, so this is a real, spec-shaped
producer contract with no live consumer to break, the same "reference
implementation before rollout" shape this platform used for
`EntitlementGateMiddleware`.

Every envelope is a real CloudEvents v1.0 envelope
(https://cloudevents.io/), not an ad hoc dict: `specversion`/`id`/
`source`/`type`/`subject`/`time`/`datacontenttype`/`data` are the
spec's own core attributes; `tenant_id`, `environment_id`,
`correlation_id`, `causation_id` are CloudEvents *extension*
attributes, which the spec explicitly allows for exactly this kind of
domain context -- the independent architecture assessment's own §3.3
required-fields list is, attribute-for-attribute, CloudEvents core
attributes plus these four extensions. `id` doubles as the delivery
idempotency key: CloudEvents' own spec defines `id` + `source` as what
a consumer dedupes redelivery on, so there is no separate field for it
here. `type` is namespaced `com.tectonic.<event>` -- CloudEvents'
own reverse-DNS convention for `type`, not a spec requirement.

Three of these -- `workflow_started`, `workflow_completed`,
`workflow_failed` -- get outbox-grade guaranteed delivery: the
scheduler writes their envelope to `event_outbox` in the same DB
transaction as the instance's own status update (see
`WorkflowRepository.update_instance_and_enqueue_event`), and
`OutboxRelayWorker` is what actually publishes them. Every other event
here stays on the pre-existing best-effort direct-publish path
(`ExecutionScheduler._publish`) -- a deliberate scope choice, not an
oversight: those top-level instance-lifecycle events are the ones
other modules most need a durability guarantee on (billing usage,
audit trails, SDK portal dashboards), while step-level and approval/
replan events are higher-volume and more tolerant of an occasional
best-effort drop. Extending outbox-grade delivery to the rest is
separate, real, unbuilt follow-up work -- see this module's README.
"""
from __future__ import annotations

import uuid
from typing import Any

from workflow_engine.core.domain import now

CLOUDEVENTS_SPECVERSION = "1.0"
SOURCE = "tectonic://workflow-engine"

TOPIC_WORKFLOW_INSTANCE = "workflow.instance"
TOPIC_WORKFLOW_STEP = "workflow.step"
TOPIC_WORKFLOW_REPLAN = "workflow.replan"
TOPIC_WORKFLOW_APPROVAL = "workflow.approval"


def envelope(
    event_type: str, *, tenant_id: str, trace_id: str, subject: str,
    environment_id: str | None = None, causation_id: str | None = None, data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "specversion": CLOUDEVENTS_SPECVERSION,
        "id": str(uuid.uuid4()),
        "source": SOURCE,
        "type": f"com.tectonic.{event_type}",
        "subject": subject,
        "time": now().isoformat(),
        "datacontenttype": "application/json",
        "tenant_id": tenant_id,
        "environment_id": environment_id,
        "correlation_id": trace_id,
        "causation_id": causation_id,
        "data": data,
    }


def workflow_started(tenant_id: str, trace_id: str, instance_id: str, definition_id: str) -> dict[str, Any]:
    return envelope(
        "workflow.started", tenant_id=tenant_id, trace_id=trace_id, subject=instance_id,
        data={"instance_id": instance_id, "definition_id": definition_id},
    )


def workflow_completed(tenant_id: str, trace_id: str, instance_id: str) -> dict[str, Any]:
    return envelope(
        "workflow.completed", tenant_id=tenant_id, trace_id=trace_id, subject=instance_id,
        data={"instance_id": instance_id},
    )


def workflow_failed(tenant_id: str, trace_id: str, instance_id: str, reason: str) -> dict[str, Any]:
    return envelope(
        "workflow.failed", tenant_id=tenant_id, trace_id=trace_id, subject=instance_id,
        data={"instance_id": instance_id, "reason": reason},
    )


def workflow_paused_for_approval(tenant_id: str, trace_id: str, instance_id: str, step_id: str) -> dict[str, Any]:
    return envelope(
        "workflow.paused_for_approval", tenant_id=tenant_id, trace_id=trace_id, subject=instance_id,
        data={"instance_id": instance_id, "step_id": step_id},
    )


def step_started(tenant_id: str, trace_id: str, instance_id: str, step_id: str, execution_mode: str) -> dict[str, Any]:
    return envelope(
        "step.started", tenant_id=tenant_id, trace_id=trace_id, subject=step_id,
        data={"instance_id": instance_id, "step_id": step_id, "execution_mode": execution_mode},
    )


def step_completed(
    tenant_id: str,
    trace_id: str,
    instance_id: str,
    step_id: str,
    execution_mode: str,
    confidence_score: float | None,
) -> dict[str, Any]:
    return envelope(
        "step.completed", tenant_id=tenant_id, trace_id=trace_id, subject=step_id,
        data={
            "instance_id": instance_id, "step_id": step_id, "execution_mode": execution_mode,
            "confidence_score": confidence_score,
        },
    )


def step_failed(
    tenant_id: str, trace_id: str, instance_id: str, step_id: str, retry_count: int, error: str
) -> dict[str, Any]:
    return envelope(
        "step.failed", tenant_id=tenant_id, trace_id=trace_id, subject=step_id,
        data={"instance_id": instance_id, "step_id": step_id, "retry_count": retry_count, "error": error},
    )


def approval_requested(
    tenant_id: str, trace_id: str, instance_id: str, step_id: str, approval_request_id: str, timeout_seconds: int
) -> dict[str, Any]:
    return envelope(
        "approval.requested", tenant_id=tenant_id, trace_id=trace_id, subject=approval_request_id,
        data={
            "instance_id": instance_id, "step_id": step_id, "approval_request_id": approval_request_id,
            "timeout_seconds": timeout_seconds,
        },
    )


def approval_resolved(
    tenant_id: str, trace_id: str, instance_id: str, step_id: str, approval_request_id: str, decision: str
) -> dict[str, Any]:
    return envelope(
        "approval.resolved", tenant_id=tenant_id, trace_id=trace_id, subject=approval_request_id,
        data={
            "instance_id": instance_id, "step_id": step_id, "approval_request_id": approval_request_id,
            "decision": decision,
        },
    )


def replan_triggered(
    tenant_id: str, trace_id: str, instance_id: str, original_step_id: str, reason: str, outcome: str
) -> dict[str, Any]:
    return envelope(
        "replan.triggered", tenant_id=tenant_id, trace_id=trace_id, subject=instance_id,
        data={"instance_id": instance_id, "original_step_id": original_step_id, "reason": reason, "outcome": outcome},
    )
