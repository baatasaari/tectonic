"""`/v1/long-term-memory/*` routes (LLD §3.1).

Two endpoints beyond the LLD's documented API table exist here as
practical additions: `POST /reflections` (Evaluation Framework, which
would trigger reflections per the LLD, doesn't exist yet as a module) and
`POST /consolidation-runs` (Workflow Engine's scheduler isn't wired to
this module yet). See the module README's "Design notes vs. the LLD".
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from long_term_memory.api.deps import (
    build_consolidation_engine,
    build_forgetting_engine,
    build_memory_service,
    build_reflection_loop,
    get_ctx,
    get_repository,
)
from long_term_memory.app_context import AppContext
from long_term_memory.core.domain import MemoryType
from long_term_memory.core.ports import LongTermMemoryRepository
from long_term_memory.schemas.memory import (
    ConsolidationRunSchema,
    DeletionRecordSchema,
    ErasureRequest,
    GenerateReflectionRequest,
    MemoryItemSchema,
    QueryRequest,
    RankedMemoryItemSchema,
    ReflectionEntryListResponse,
    ReflectionEntrySchema,
    StoreItemRequest,
)

router = APIRouter(prefix="/v1/long-term-memory", tags=["long-term-memory"])


def _tenant_id(request: Request, ctx: AppContext) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


def _item_schema(item) -> MemoryItemSchema:
    return MemoryItemSchema(
        id=item.id, scope=item.scope, memory_type=item.memory_type.value, content=item.content,
        visibility_policy_ref=item.visibility_policy_ref, vector_ref=item.vector_ref, graph_ref=item.graph_ref,
        status=item.status.value, relevance_score=item.relevance_score, created_at=item.created_at,
        last_accessed_at=item.last_accessed_at,
    )


@router.post("/items", response_model=MemoryItemSchema, status_code=201)
async def store_item(
    body: StoreItemRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: LongTermMemoryRepository = Depends(get_repository),
) -> MemoryItemSchema:
    service = build_memory_service(ctx, repository)
    try:
        memory_type = MemoryType(body.memory_type)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"invalid memory_type: {body.memory_type!r}") from e

    item = await service.store(
        tenant_id=_tenant_id(request, ctx), scope=body.scope, memory_type=memory_type, content=body.content,
        visibility_policy_ref=body.visibility_policy_ref,
    )
    return _item_schema(item)


@router.post("/query", response_model=list[RankedMemoryItemSchema])
async def query_items(
    # Deliberately NOT given limit/offset pagination: this is a
    # ranked-results endpoint, not a listing endpoint. `body.top_k`
    # (QueryRequest, default 10) already caps the result count the same
    # way pagination would bound it — `MemoryService.query` ranks all
    # candidate matches by relevance and slices to `results[:top_k]`
    # before returning, so the response is already bounded and there is
    # no "next page" of lower-ranked results a client would legitimately
    # want to walk; they'd re-query with a larger top_k instead. See the
    # module README's "Design notes vs. the LLD".
    body: QueryRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: LongTermMemoryRepository = Depends(get_repository),
) -> list[RankedMemoryItemSchema]:
    service = build_memory_service(ctx, repository)
    memory_types = [MemoryType(t) for t in body.memory_types] if body.memory_types else None
    ranked = await service.query(
        tenant_id=_tenant_id(request, ctx), scope=body.scope, query=body.query, memory_types=memory_types,
        top_k=body.top_k, requesting_agent=body.requesting_agent,
    )
    return [RankedMemoryItemSchema(item=_item_schema(r.item), score=r.score) for r in ranked]


@router.get("/reflections", response_model=ReflectionEntryListResponse)
async def list_reflections(
    agent_ref: str,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: AppContext = Depends(get_ctx),
    repository: LongTermMemoryRepository = Depends(get_repository),
) -> ReflectionEntryListResponse:
    loop = build_reflection_loop(ctx, repository)
    entries, total = await loop.list_for_agent(_tenant_id(request, ctx), agent_ref, limit=limit, offset=offset)
    return ReflectionEntryListResponse(
        items=[
            ReflectionEntrySchema(
                id=e.id, agent_ref=e.agent_ref, triggering_interaction_ref=e.triggering_interaction_ref,
                reflection_content=e.reflection_content, applied=e.applied, created_at=e.created_at,
            )
            for e in entries
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/reflections", response_model=ReflectionEntrySchema, status_code=201)
async def generate_reflection(
    body: GenerateReflectionRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: LongTermMemoryRepository = Depends(get_repository),
) -> ReflectionEntrySchema:
    loop = build_reflection_loop(ctx, repository)
    entry = await loop.generate(_tenant_id(request, ctx), body.agent_ref, body.triggering_interaction_ref, body.context)
    return ReflectionEntrySchema(
        id=entry.id, agent_ref=entry.agent_ref, triggering_interaction_ref=entry.triggering_interaction_ref,
        reflection_content=entry.reflection_content, applied=entry.applied, created_at=entry.created_at,
    )


@router.post("/erasure-requests", response_model=DeletionRecordSchema, status_code=201)
async def create_erasure_request(
    body: ErasureRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: LongTermMemoryRepository = Depends(get_repository),
) -> DeletionRecordSchema:
    engine = build_forgetting_engine(ctx, repository)
    record = await engine.execute(_tenant_id(request, ctx), body.subject_ref, body.requested_by)
    return DeletionRecordSchema(
        id=record.id, subject_ref=record.subject_ref, status="completed",
        memory_items_deleted=record.memory_items_deleted, deletion_proof_hash=record.deletion_proof_hash,
        requested_by=record.requested_by, completed_at=record.completed_at,
    )


@router.get("/erasure-requests/{deletion_id}", response_model=DeletionRecordSchema)
async def get_erasure_request(
    deletion_id: str,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: LongTermMemoryRepository = Depends(get_repository),
) -> DeletionRecordSchema:
    record = await repository.get_deletion_record(_tenant_id(request, ctx), deletion_id)
    if record is None:
        raise HTTPException(status_code=404, detail="deletion record not found")
    return DeletionRecordSchema(
        id=record.id, subject_ref=record.subject_ref, status="completed",
        memory_items_deleted=record.memory_items_deleted, deletion_proof_hash=record.deletion_proof_hash,
        requested_by=record.requested_by, completed_at=record.completed_at,
    )


@router.post("/consolidation-runs", response_model=ConsolidationRunSchema, status_code=201)
async def run_consolidation(
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: LongTermMemoryRepository = Depends(get_repository),
) -> ConsolidationRunSchema:
    engine = build_consolidation_engine(ctx, repository)
    run = await engine.run(_tenant_id(request, ctx))
    return ConsolidationRunSchema(
        id=run.id, items_merged_count=run.items_merged_count, items_decayed_count=run.items_decayed_count,
        run_at=run.run_at,
    )
