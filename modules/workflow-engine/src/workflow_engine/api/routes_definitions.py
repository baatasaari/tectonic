"""`/v1/workflow-engine/definitions` routes (LLD §3.3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from workflow_engine.api.deps import get_ctx, get_repository
from workflow_engine.app_context import AppContext
from workflow_engine.core.domain import DefinitionStatus, WorkflowDefinitionRecord, new_id
from workflow_engine.core.parser import GraphValidationError, parse_and_validate
from workflow_engine.core.ports import WorkflowRepository
from workflow_engine.schemas.definitions import (
    CreateDefinitionRequest,
    DefinitionDetail,
    DefinitionSummary,
    PublishDefinitionResponse,
)

router = APIRouter(prefix="/v1/workflow-engine/definitions", tags=["definitions"])


def _tenant_id(request: Request, ctx: AppContext) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


def _created_by(request: Request) -> str:
    return request.headers.get("X-User-Id", "unknown")


@router.post("", response_model=DefinitionSummary, status_code=201)
async def create_definition(
    body: CreateDefinitionRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: WorkflowRepository = Depends(get_repository),
) -> DefinitionSummary:
    graph_schema_dict = body.graph_schema.model_dump(by_alias=True)
    try:
        parse_and_validate(graph_schema_dict)
    except GraphValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors) from e

    record = WorkflowDefinitionRecord(
        id=new_id(),
        name=body.name,
        version=1,
        status=DefinitionStatus.DRAFT,
        graph_schema=graph_schema_dict,
        tenant_id=_tenant_id(request, ctx),
        created_by=_created_by(request),
    )
    record = await repository.create_definition(record)
    return DefinitionSummary(id=record.id, version=record.version, status=record.status.value)


@router.post("/{definition_id}/publish", response_model=PublishDefinitionResponse)
async def publish_definition(
    definition_id: str,
    repository: WorkflowRepository = Depends(get_repository),
) -> PublishDefinitionResponse:
    existing = await repository.get_definition(definition_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="definition not found")

    try:
        parse_and_validate(existing.graph_schema)
    except GraphValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors) from e

    record = await repository.publish_definition(definition_id)
    return PublishDefinitionResponse(status=record.status.value, published_at=record.published_at)


@router.get("/{definition_id}", response_model=DefinitionDetail)
async def get_definition(
    definition_id: str,
    repository: WorkflowRepository = Depends(get_repository),
) -> DefinitionDetail:
    record = await repository.get_definition(definition_id)
    if record is None:
        raise HTTPException(status_code=404, detail="definition not found")
    return DefinitionDetail(
        id=record.id,
        name=record.name,
        version=record.version,
        status=record.status.value,
        graph_schema=record.graph_schema,
        tenant_id=record.tenant_id,
        created_by=record.created_by,
        created_at=record.created_at,
        published_at=record.published_at,
    )
