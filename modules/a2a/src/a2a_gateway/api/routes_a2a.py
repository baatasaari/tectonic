"""`/v1/a2a/*` routes (LLD §3). `/.well-known/agent.json` is deliberately
NOT under this router -- it lives at the app root in `main.py`, per the
A2A spec's own well-known-endpoint convention.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from a2a_gateway.api.deps import (
    build_delegation_service,
    build_rpc_gateway,
    get_ctx,
    get_repository,
    resolve_caller_agent_id,
    resolve_caller_agent_url,
    resolve_tenant_id,
)
from a2a_gateway.app_context import AppContext
from a2a_gateway.core.domain import (
    A2AAccessPolicyRecord,
    A2ATaskNotFoundError,
    SkillNotAdvertisedError,
    TaskDirection,
    TaskStatus,
    new_id,
)
from a2a_gateway.core.ports import A2AGatewayRepository
from a2a_gateway.schemas.a2a import (
    AccessPolicySchema,
    DelegateRequest,
    JsonRpcRequestSchema,
    JsonRpcResponseSchema,
    SetAccessPolicyRequest,
    TaskListResponse,
    TaskSchema,
)

router = APIRouter(prefix="/v1/a2a", tags=["a2a"])


def _task_schema(task) -> TaskSchema:
    return TaskSchema(
        id=task.id, tenant_id=task.tenant_id, direction=task.direction.value, peer_agent_url=task.peer_agent_url,
        skill_id=task.skill_id, status=task.status.value, input_message=task.input_message,
        output_artifacts=task.output_artifacts, error=task.error, created_at=task.created_at, updated_at=task.updated_at,
    )


@router.post("/delegate", response_model=TaskSchema, status_code=201)
async def delegate(
    body: DelegateRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    ctx: AppContext = Depends(get_ctx),
    repository: A2AGatewayRepository = Depends(get_repository),
) -> TaskSchema:
    service = build_delegation_service(repository, ctx)
    try:
        task = await service.delegate(
            tenant_id=tenant_id, target_agent_url=body.target_agent_url, skill_id=body.skill_id,
            input_message=body.input_message,
        )
    except SkillNotAdvertisedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _task_schema(task)


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    tenant_id: str | None = Query(None),
    direction: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: A2AGatewayRepository = Depends(get_repository),
) -> TaskListResponse:
    parsed_direction = TaskDirection(direction) if direction else None
    tasks, total = await repository.list_tasks(tenant_id=tenant_id, direction=parsed_direction, limit=limit, offset=offset)
    return TaskListResponse(items=[_task_schema(t) for t in tasks], total=total, limit=limit, offset=offset)


@router.get("/tasks/{task_id}", response_model=TaskSchema)
async def get_task(
    task_id: str,
    repository: A2AGatewayRepository = Depends(get_repository),
) -> TaskSchema:
    task = await repository.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=str(A2ATaskNotFoundError(task_id)))
    return _task_schema(task)


@router.post("/tasks/{task_id}/cancel", response_model=TaskSchema)
async def cancel_task(
    task_id: str,
    repository: A2AGatewayRepository = Depends(get_repository),
) -> TaskSchema:
    task = await repository.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=str(A2ATaskNotFoundError(task_id)))
    canceled = await repository.update_task_status(task_id, status=TaskStatus.CANCELED)
    return _task_schema(canceled)


@router.put("/access-policies/{caller_agent_id}", response_model=AccessPolicySchema)
async def set_access_policy(
    caller_agent_id: str,
    body: SetAccessPolicyRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    repository: A2AGatewayRepository = Depends(get_repository),
) -> AccessPolicySchema:
    record = A2AAccessPolicyRecord(
        id=new_id(), caller_agent_id=caller_agent_id, tenant_id=tenant_id, allowed_skills=body.allowed_skills,
    )
    saved = await repository.upsert_access_policy(record)
    return AccessPolicySchema(
        caller_agent_id=saved.caller_agent_id, tenant_id=saved.tenant_id, allowed_skills=saved.allowed_skills,
    )


@router.post("/rpc", response_model=JsonRpcResponseSchema)
async def rpc(
    body: JsonRpcRequestSchema,
    tenant_id: str = Depends(resolve_tenant_id),
    caller_agent_id: str = Depends(resolve_caller_agent_id),
    peer_agent_url: str = Depends(resolve_caller_agent_url),
    ctx: AppContext = Depends(get_ctx),
    repository: A2AGatewayRepository = Depends(get_repository),
) -> JsonRpcResponseSchema:
    gateway = build_rpc_gateway(repository, ctx)
    response = await gateway.handle(
        method=body.method, params=body.params, id=body.id, tenant_id=tenant_id,
        caller_agent_id=caller_agent_id, peer_agent_url=peer_agent_url,
    )
    return JsonRpcResponseSchema(jsonrpc=response.jsonrpc, id=response.id, result=response.result, error=response.error)
