"""SQLAlchemy-backed implementation of WorkflowRepository (LLD §3.1, §4.10).

All queries are tenant-scoped by construction where the caller supplies a
tenant_id; multi-tenancy isolation is enforced at the query layer per the
non-functional targets table.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from workflow_engine.core.domain import (
    ApprovalRequestRecord,
    ApprovalStatus,
    DefinitionStatus,
    EventOutboxRecord,
    ExecutionMode,
    InstanceStatus,
    OutboxEventStatus,
    ReplanEventRecord,
    StepExecutionRecord,
    StepStatus,
    WorkflowDefinitionRecord,
    WorkflowInstanceRecord,
    now,
)
from workflow_engine.db import models


def _def_to_domain(m: models.WorkflowDefinition) -> WorkflowDefinitionRecord:
    return WorkflowDefinitionRecord(
        id=str(m.id),
        name=m.name,
        version=m.version,
        status=DefinitionStatus(m.status),
        graph_schema=m.graph_schema,
        tenant_id=m.tenant_id,
        created_by=m.created_by,
        created_at=m.created_at,
        published_at=m.published_at,
    )


def _instance_to_domain(m: models.WorkflowInstance) -> WorkflowInstanceRecord:
    return WorkflowInstanceRecord(
        id=str(m.id),
        definition_id=str(m.definition_id),
        definition_version=m.definition_version,
        tenant_id=m.tenant_id,
        trace_id=m.trace_id,
        status=InstanceStatus(m.status),
        current_step_ids=list(m.current_step_ids or []),
        context=dict(m.context or {}),
        started_at=m.started_at,
        completed_at=m.completed_at,
    )


def _outbox_to_domain(m: models.EventOutbox) -> EventOutboxRecord:
    return EventOutboxRecord(
        id=str(m.id), topic=m.topic, tenant_id=m.tenant_id, envelope=dict(m.envelope or {}),
        status=OutboxEventStatus(m.status), attempts=m.attempts, worker_id=m.worker_id,
        lease_expires_at=m.lease_expires_at, last_error=m.last_error,
        created_at=m.created_at, published_at=m.published_at,
    )


def _step_to_domain(m: models.StepExecution) -> StepExecutionRecord:
    return StepExecutionRecord(
        id=str(m.id),
        instance_id=str(m.instance_id),
        step_id=m.step_id,
        execution_mode=ExecutionMode(m.execution_mode),
        status=StepStatus(m.status),
        input_snapshot=dict(m.input_snapshot or {}),
        output=m.output,
        confidence_score=m.confidence_score,
        retry_count=m.retry_count,
        started_at=m.started_at,
        completed_at=m.completed_at,
    )


def _approval_to_domain(m: models.ApprovalRequest) -> ApprovalRequestRecord:
    return ApprovalRequestRecord(
        id=str(m.id),
        step_execution_id=str(m.step_execution_id),
        human_oversight_ref_id=m.human_oversight_ref_id,
        status=ApprovalStatus(m.status),
        requested_at=m.requested_at,
        resolved_at=m.resolved_at,
    )


def _is_valid_uuid(value: str) -> bool:
    """`id` columns are Postgres `UUID`; a path-param `str` that isn't a
    syntactically valid UUID by definition names no row, but handing it
    to `asyncpg` regardless raises an unhandled `ValueError`/`DataError`
    deep in the driver instead of the caller's own `None`/404 path
    (found by this module's own OpenAPI contract-test tier -- see
    Billing and Metering's `db/repository.py` for the original instance
    of this exact fix). Callers to a `get_*`/lookup-by-externally-
    supplied-id method must check this first."""
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


class SQLAlchemyWorkflowRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_definition(self, definition_id: str) -> WorkflowDefinitionRecord | None:
        if not _is_valid_uuid(definition_id):
            return None
        m = await self.session.get(models.WorkflowDefinition, definition_id)
        return _def_to_domain(m) if m else None

    async def get_definition_by_name(self, name: str, tenant_id: str) -> WorkflowDefinitionRecord | None:
        rows = await self.session.execute(
            select(models.WorkflowDefinition)
            .where(models.WorkflowDefinition.name == name, models.WorkflowDefinition.tenant_id == tenant_id)
            .order_by(models.WorkflowDefinition.version.desc())
            .limit(1)
        )
        m = rows.scalars().first()
        return _def_to_domain(m) if m else None

    async def create_definition(self, record: WorkflowDefinitionRecord) -> WorkflowDefinitionRecord:
        m = models.WorkflowDefinition(
            id=record.id,
            name=record.name,
            version=record.version,
            status=record.status.value,
            graph_schema=record.graph_schema,
            tenant_id=record.tenant_id,
            created_by=record.created_by,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _def_to_domain(m)

    async def publish_definition(self, definition_id: str) -> WorkflowDefinitionRecord:
        m = await self.session.get(models.WorkflowDefinition, definition_id)
        if m is None:
            raise LookupError(definition_id)
        m.status = DefinitionStatus.PUBLISHED.value
        m.published_at = now()
        await self.session.commit()
        await self.session.refresh(m)
        return _def_to_domain(m)

    async def create_instance(self, record: WorkflowInstanceRecord) -> WorkflowInstanceRecord:
        m = models.WorkflowInstance(
            id=record.id,
            definition_id=record.definition_id,
            definition_version=record.definition_version,
            status=record.status.value,
            current_step_ids=record.current_step_ids,
            context=record.context,
            tenant_id=record.tenant_id,
            trace_id=record.trace_id,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _instance_to_domain(m)

    async def get_instance(self, instance_id: str) -> WorkflowInstanceRecord | None:
        if not _is_valid_uuid(instance_id):
            return None
        m = await self.session.get(models.WorkflowInstance, instance_id)
        return _instance_to_domain(m) if m else None

    async def update_instance(self, record: WorkflowInstanceRecord) -> WorkflowInstanceRecord:
        m = await self.session.get(models.WorkflowInstance, record.id)
        if m is None:
            raise LookupError(record.id)
        m.status = record.status.value
        m.current_step_ids = record.current_step_ids
        m.context = record.context
        m.completed_at = record.completed_at
        await self.session.commit()
        await self.session.refresh(m)
        return _instance_to_domain(m)

    async def create_step_execution(self, record: StepExecutionRecord) -> StepExecutionRecord:
        m = models.StepExecution(
            id=record.id,
            instance_id=record.instance_id,
            step_id=record.step_id,
            execution_mode=record.execution_mode.value,
            status=record.status.value,
            input_snapshot=record.input_snapshot,
            output=record.output,
            confidence_score=record.confidence_score,
            retry_count=record.retry_count,
            started_at=record.started_at,
            completed_at=record.completed_at,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _step_to_domain(m)

    async def update_step_execution(self, record: StepExecutionRecord) -> StepExecutionRecord:
        m = await self.session.get(models.StepExecution, record.id)
        if m is None:
            raise LookupError(record.id)
        m.status = record.status.value
        m.output = record.output
        m.confidence_score = record.confidence_score
        m.retry_count = record.retry_count
        m.started_at = record.started_at
        m.completed_at = record.completed_at
        await self.session.commit()
        await self.session.refresh(m)
        return _step_to_domain(m)

    async def list_step_executions(
        self, instance_id: str, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[StepExecutionRecord], int]:
        # `GET /instances/{instance_id}/steps` (routes_instances.py) calls this
        # directly with the raw path param, with no existence check of its own first --
        # a syntactically-invalid UUID by definition matches no instance's steps, so
        # this returns the same empty result a real-but-unknown UUID would, rather
        # than handing an un-castable string to asyncpg (found by this module's own
        # OpenAPI contract-test tier).
        if not _is_valid_uuid(instance_id):
            return [], 0
        filters = [models.StepExecution.instance_id == instance_id]

        count_stmt = select(func.count(models.StepExecution.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        # No non-nullable timestamp column on this table (started_at/completed_at are both
        # nullable — a pending step has neither) — order by id ascending as a stable,
        # deterministic last resort so limit/offset pagination is meaningful.
        stmt = (
            select(models.StepExecution)
            .where(*filters)
            .order_by(models.StepExecution.id.asc())
            .limit(limit)
            .offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_step_to_domain(m) for m in rows.scalars().all()], total

    async def get_step_execution(self, step_execution_id: str) -> StepExecutionRecord | None:
        if not _is_valid_uuid(step_execution_id):
            return None
        m = await self.session.get(models.StepExecution, step_execution_id)
        return _step_to_domain(m) if m else None

    async def create_approval_request(self, record: ApprovalRequestRecord) -> ApprovalRequestRecord:
        m = models.ApprovalRequest(
            id=record.id,
            step_execution_id=record.step_execution_id,
            human_oversight_ref_id=record.human_oversight_ref_id,
            status=record.status.value,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _approval_to_domain(m)

    async def get_approval_request(self, approval_id: str) -> ApprovalRequestRecord | None:
        if not _is_valid_uuid(approval_id):
            return None
        m = await self.session.get(models.ApprovalRequest, approval_id)
        return _approval_to_domain(m) if m else None

    async def update_approval_request(self, record: ApprovalRequestRecord) -> ApprovalRequestRecord:
        m = await self.session.get(models.ApprovalRequest, record.id)
        if m is None:
            raise LookupError(record.id)
        m.status = record.status.value
        m.human_oversight_ref_id = record.human_oversight_ref_id
        m.resolved_at = record.resolved_at
        await self.session.commit()
        await self.session.refresh(m)
        return _approval_to_domain(m)

    async def create_replan_event(self, record: ReplanEventRecord) -> ReplanEventRecord:
        m = models.ReplanEvent(
            id=record.id,
            instance_id=record.instance_id,
            trigger_reason=record.trigger_reason,
            original_step_id=record.original_step_id,
            new_graph_delta=record.new_graph_delta,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return ReplanEventRecord(
            id=str(m.id),
            instance_id=str(m.instance_id),
            trigger_reason=m.trigger_reason,
            original_step_id=m.original_step_id,
            new_graph_delta=m.new_graph_delta,
            created_at=m.created_at,
        )

    # --- Transactional event outbox ---

    async def update_instance_and_enqueue_event(
        self, record: WorkflowInstanceRecord, *, topic: str, envelope: dict[str, Any],
    ) -> WorkflowInstanceRecord:
        m = await self.session.get(models.WorkflowInstance, record.id)
        if m is None:
            raise LookupError(record.id)
        m.status = record.status.value
        m.current_step_ids = record.current_step_ids
        m.context = record.context
        m.completed_at = record.completed_at

        outbox_row = models.EventOutbox(
            id=envelope["id"], topic=topic, tenant_id=envelope["tenant_id"], envelope=envelope,
        )
        self.session.add(outbox_row)

        # One commit for both writes -- the whole point of the outbox pattern: if this
        # transaction commits, the instance's new state and its accompanying event are
        # guaranteed to both be there; if it rolls back, neither is.
        await self.session.commit()
        await self.session.refresh(m)
        return _instance_to_domain(m)

    async def claim_next_outbox_event(self, worker_id: str, lease_seconds: int) -> EventOutboxRecord | None:
        """`SELECT ... FOR UPDATE SKIP LOCKED`: the row-level lock this
        takes is what lets multiple worker processes/pods poll
        concurrently without two of them ever claiming the same pending
        event — a competing claimant simply skips a row another
        transaction already has locked, rather than blocking on it or
        double-claiming it. Same shape `claim_next_evidence_pack`
        (Regulatory Compliance) already established."""
        moment = now()
        stmt = (
            select(models.EventOutbox)
            .where(
                models.EventOutbox.status == OutboxEventStatus.PENDING.value,
                (models.EventOutbox.lease_expires_at.is_(None)) | (models.EventOutbox.lease_expires_at < moment),
            )
            .order_by(models.EventOutbox.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        rows = await self.session.execute(stmt)
        m = rows.scalars().first()
        if m is None:
            return None
        m.worker_id = worker_id
        m.attempts += 1
        m.lease_expires_at = moment + timedelta(seconds=lease_seconds)
        await self.session.commit()
        await self.session.refresh(m)
        return _outbox_to_domain(m)

    async def mark_outbox_event_published(self, event_id: str) -> None:
        m = await self.session.get(models.EventOutbox, event_id)
        if m is None:
            return
        m.status = OutboxEventStatus.PUBLISHED.value
        m.published_at = now()
        m.lease_expires_at = None
        await self.session.commit()

    async def requeue_outbox_event_for_retry(self, event_id: str, *, error: str) -> None:
        m = await self.session.get(models.EventOutbox, event_id)
        if m is None:
            return
        m.lease_expires_at = None
        m.last_error = error[:1024]
        await self.session.commit()

    async def fail_exhausted_outbox_events(self, max_attempts: int) -> int:
        result = await self.session.execute(
            update(models.EventOutbox)
            .where(
                models.EventOutbox.status == OutboxEventStatus.PENDING.value,
                models.EventOutbox.attempts >= max_attempts,
            )
            .values(status=OutboxEventStatus.FAILED.value, last_error=f"exceeded max attempts ({max_attempts})")
        )
        await self.session.commit()
        return result.rowcount or 0

    async def force_expire_stale_outbox_leases(self) -> int:
        moment = now()
        result = await self.session.execute(
            update(models.EventOutbox)
            .where(
                models.EventOutbox.status == OutboxEventStatus.PENDING.value,
                models.EventOutbox.lease_expires_at.is_not(None),
                models.EventOutbox.lease_expires_at > moment,
            )
            .values(lease_expires_at=moment)
        )
        await self.session.commit()
        return result.rowcount or 0
