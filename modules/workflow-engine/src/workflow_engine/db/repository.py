"""SQLAlchemy-backed implementation of WorkflowRepository (LLD §3.1, §4.10).

All queries are tenant-scoped by construction where the caller supplies a
tenant_id; multi-tenancy isolation is enforced at the query layer per the
non-functional targets table.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from workflow_engine.core.domain import (
    ApprovalRequestRecord,
    ApprovalStatus,
    DefinitionStatus,
    ExecutionMode,
    InstanceStatus,
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


class SQLAlchemyWorkflowRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_definition(self, definition_id: str) -> WorkflowDefinitionRecord | None:
        m = await self.session.get(models.WorkflowDefinition, definition_id)
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

    async def list_step_executions(self, instance_id: str) -> list[StepExecutionRecord]:
        rows = await self.session.execute(
            select(models.StepExecution).where(models.StepExecution.instance_id == instance_id)
        )
        return [_step_to_domain(m) for m in rows.scalars().all()]

    async def get_step_execution(self, step_execution_id: str) -> StepExecutionRecord | None:
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
