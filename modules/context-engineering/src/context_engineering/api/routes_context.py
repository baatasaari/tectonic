"""`/v1/context-engineering/*` routes (LLD §3.3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from context_engineering.api.deps import build_assembly_service, get_ctx, get_repository
from context_engineering.app_context import AppContext
from context_engineering.core.domain import CandidateItem, OntologyConfigRecord, new_id
from context_engineering.core.ports import ContextRepository
from context_engineering.schemas.context import (
    AssembleRequest,
    AssembleResponse,
    CreateOntologyRequest,
    OntologySummary,
    WeightsResponse,
)

router = APIRouter(prefix="/v1/context-engineering", tags=["context-engineering"])


def _tenant_id(request: Request, ctx: AppContext) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


@router.post("/assemble", response_model=AssembleResponse)
async def assemble(
    body: AssembleRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: ContextRepository = Depends(get_repository),
) -> AssembleResponse:
    tenant_id = _tenant_id(request, ctx)
    service = build_assembly_service(ctx, repository)

    result = await service.assemble(
        candidate_items=[CandidateItem(source=i.source, content=i.content, metadata=i.metadata) for i in body.candidate_items],
        token_budget=body.token_budget or ctx.settings.budget.default_token_budget,
        task_type=body.task_type,
        tenant_id=tenant_id,
        request_ref=body.request_ref or new_id(),
    )
    return AssembleResponse(
        assembled_context=result.assembled_context,
        tokens_used=result.tokens_used,
        items_dropped_count=result.items_dropped_count,
        items_included_count=result.items_included_count,
        items_summarised_count=result.items_summarised_count,
    )


@router.post("/ontologies", response_model=OntologySummary, status_code=201)
async def create_ontology(
    body: CreateOntologyRequest,
    repository: ContextRepository = Depends(get_repository),
) -> OntologySummary:
    existing = await repository.get_active_ontology(body.tenant_id)
    next_version = (existing.version + 1) if existing else 1

    record = OntologyConfigRecord(
        id=new_id(), tenant_id=body.tenant_id, version=next_version,
        roles=body.roles, entity_types=body.entity_types, policy_tags=body.policy_tags,
    )
    record = await repository.create_ontology(record)
    return OntologySummary(id=record.id, version=record.version)


@router.get("/weights/{task_type}", response_model=WeightsResponse)
async def get_weights(
    task_type: str,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: ContextRepository = Depends(get_repository),
) -> WeightsResponse:
    tenant_id = _tenant_id(request, ctx)
    record = await repository.get_weights(tenant_id, task_type)
    if record is not None:
        return WeightsResponse(task_type=task_type, feature_weights=record.feature_weights)

    default_weights = ctx.settings.prioritisation.default_task_type_weights.get(task_type)
    if default_weights is None:
        raise HTTPException(status_code=404, detail=f"no weights (learned or default) for task_type '{task_type}'")
    return WeightsResponse(task_type=task_type, feature_weights=default_weights)
