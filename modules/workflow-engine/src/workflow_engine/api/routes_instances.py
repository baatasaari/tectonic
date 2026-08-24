"""`/v1/workflow-engine/instances` routes (LLD §3.3, §3.4)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from workflow_engine.api.deps import build_scheduler, get_ctx, get_repository
from workflow_engine.app_context import AppContext
from workflow_engine.core.domain import (
    ApprovalStatus,
    InstanceStatus,
    WorkflowInstanceRecord,
    new_id,
    now,
)
from workflow_engine.core.parser import parse_and_validate
from workflow_engine.core.ports import WorkflowRepository
from workflow_engine.schemas.instances import (
    ApprovalCallbackRequest,
    InstanceDetail,
    PauseRequest,
    StartInstanceRequest,
    StartInstanceResponse,
    StatusResponse,
    StepExecutionListResponse,
    StepExecutionSummary,
    TerminateRequest,
)

router = APIRouter(prefix="/v1/workflow-engine/instances", tags=["instances"])


def _tenant_id(request: Request, ctx: AppContext) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


@router.post("", response_model=StartInstanceResponse, status_code=201)
async def start_instance(
    body: StartInstanceRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: WorkflowRepository = Depends(get_repository),
) -> StartInstanceResponse:
    definition = await repository.get_definition(body.definition_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="definition not found")
    if body.definition_version is not None and body.definition_version != definition.version:
        raise HTTPException(status_code=409, detail="requested definition_version does not match stored version")

    graph = parse_and_validate(definition.graph_schema)

    trace_id = uuid.uuid4().hex
    instance = WorkflowInstanceRecord(
        id=new_id(),
        definition_id=definition.id,
        definition_version=definition.version,
        tenant_id=_tenant_id(request, ctx),
        trace_id=trace_id,
        context=dict(body.initial_context),
    )
    instance = await repository.create_instance(instance)

    scheduler = build_scheduler(ctx, repository)
    instance = await scheduler.start(instance, graph)

    return StartInstanceResponse(id=instance.id, status=instance.status.value, trace_id=instance.trace_id)


@router.get("/{instance_id}", response_model=InstanceDetail)
async def get_instance(
    instance_id: str,
    repository: WorkflowRepository = Depends(get_repository),
) -> InstanceDetail:
    instance = await repository.get_instance(instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="instance not found")
    # `InstanceDetail.steps` is the complete step list for this one instance, not the
    # paginated `/steps` resource — limit=10_000 is an effectively-unbounded internal page
    # size (one instance's step count is bounded by its workflow graph).
    steps, _total = await repository.list_step_executions(instance_id, limit=10_000)
    return InstanceDetail(
        id=instance.id,
        definition_id=instance.definition_id,
        definition_version=instance.definition_version,
        status=instance.status.value,
        current_step_ids=instance.current_step_ids,
        context=instance.context,
        tenant_id=instance.tenant_id,
        trace_id=instance.trace_id,
        started_at=instance.started_at,
        completed_at=instance.completed_at,
        steps=[_step_summary(s) for s in steps],
    )


@router.get("/{instance_id}/steps", response_model=list[StepExecutionSummary])
async def list_steps(
    instance_id: str,
    repository: WorkflowRepository = Depends(get_repository),
) -> list[StepExecutionSummary]:
    steps = await repository.list_step_executions(instance_id)
    return [_step_summary(s) for s in steps]


@router.post("/{instance_id}/pause", response_model=StatusResponse)
async def pause_instance(
    instance_id: str,
    body: PauseRequest,
    repository: WorkflowRepository = Depends(get_repository),
) -> StatusResponse:
    instance = await repository.get_instance(instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="instance not found")
    if instance.status != InstanceStatus.RUNNING:
        raise HTTPException(status_code=409, detail=f"cannot pause instance in status {instance.status.value}")
    instance.status = InstanceStatus.PAUSED_FOR_APPROVAL
    instance = await repository.update_instance(instance)
    return StatusResponse(status=instance.status.value)


@router.post("/{instance_id}/resume", response_model=StatusResponse)
async def resume_instance(
    instance_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: WorkflowRepository = Depends(get_repository),
) -> StatusResponse:
    instance = await repository.get_instance(instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="instance not found")
    if instance.status != InstanceStatus.PAUSED_FOR_APPROVAL:
        raise HTTPException(status_code=409, detail=f"cannot resume instance in status {instance.status.value}")

    definition = await repository.get_definition(instance.definition_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="definition not found")
    graph = parse_and_validate(definition.graph_schema)

    scheduler = build_scheduler(ctx, repository)
    instance = await scheduler.resume_after_approval(instance, graph, approved=True)
    return StatusResponse(status=instance.status.value)


@router.post("/{instance_id}/terminate", response_model=StatusResponse)
async def terminate_instance(
    instance_id: str,
    body: TerminateRequest,
    repository: WorkflowRepository = Depends(get_repository),
) -> StatusResponse:
    instance = await repository.get_instance(instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="instance not found")
    if instance.status in (InstanceStatus.COMPLETED, InstanceStatus.FAILED, InstanceStatus.TERMINATED):
        raise HTTPException(status_code=409, detail=f"cannot terminate instance in status {instance.status.value}")
    instance.status = InstanceStatus.TERMINATED
    instance.completed_at = now()
    instance = await repository.update_instance(instance)
    return StatusResponse(status=instance.status.value)


@router.post("/{instance_id}/approvals/{approval_id}/callback", response_model=StatusResponse)
async def approval_callback(
    instance_id: str,
    approval_id: str,
    body: ApprovalCallbackRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: WorkflowRepository = Depends(get_repository),
) -> StatusResponse:
    approval = await repository.get_approval_request(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="approval request not found")
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="decision must be 'approved' or 'rejected'")

    approval.status = ApprovalStatus.APPROVED if body.decision == "approved" else ApprovalStatus.REJECTED
    approval.resolved_at = now()
    await repository.update_approval_request(approval)

    instance = await repository.get_instance(instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="instance not found")
    if instance.status != InstanceStatus.PAUSED_FOR_APPROVAL:
        return StatusResponse(status=instance.status.value)

    definition = await repository.get_definition(instance.definition_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="definition not found")
    graph = parse_and_validate(definition.graph_schema)

    scheduler = build_scheduler(ctx, repository)
    instance = await scheduler.resume_after_approval(instance, graph, approved=body.decision == "approved")
    return StatusResponse(status=instance.status.value)


def _step_summary(s) -> StepExecutionSummary:
    return StepExecutionSummary(
        id=s.id,
        step_id=s.step_id,
        execution_mode=s.execution_mode.value,
        status=s.status.value,
        confidence_score=s.confidence_score,
        retry_count=s.retry_count,
        started_at=s.started_at,
        completed_at=s.completed_at,
    )
