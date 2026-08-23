"""`/v1/vector-db/*` routes (LLD §3)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from vector_db.api.deps import get_ctx
from vector_db.app_context import AppContext
from vector_db.core.domain import MigrationNotFoundError, PointNotFoundError
from vector_db.schemas.vectors import (
    DeleteResponse,
    IndexPointRequest,
    IndexPointResponse,
    MigrationResponse,
    MigrationStatusResponse,
    QueryRequest,
    QueryResponse,
    ScoredResultSchema,
    StartMigrationRequest,
)
from vector_db.telemetry.logging import get_logger

logger = get_logger(component="routes_vectors")

router = APIRouter(prefix="/v1/vector-db", tags=["vector-db"])

_background_tasks: set[asyncio.Task] = set()


def _run_migration_in_background(ctx: AppContext, migration_id: str) -> None:
    task = asyncio.create_task(ctx.migration_manager.run(migration_id))
    _background_tasks.add(task)

    def _on_done(t: asyncio.Task) -> None:
        _background_tasks.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.error("migration_failed", migration_id=migration_id, error=str(exc))

    task.add_done_callback(_on_done)


@router.post("/points", response_model=IndexPointResponse, status_code=201)
async def index_point(
    body: IndexPointRequest,
    ctx: AppContext = Depends(get_ctx),
) -> IndexPointResponse:
    point_id = await ctx.vector_service.index_point(
        tenant_id=body.tenant_id, source_module=body.source_module, source_ref=body.source_ref,
        content=body.content, vector=body.vector, payload_extra=body.payload,
        embedding_model_version=body.embedding_model_version,
    )
    return IndexPointResponse(id=point_id)


@router.delete("/points/{point_id}", response_model=DeleteResponse)
async def delete_point(
    point_id: str,
    tenant_id: str,
    ctx: AppContext = Depends(get_ctx),
) -> DeleteResponse:
    try:
        await ctx.vector_service.delete_point(tenant_id, point_id)
    except PointNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return DeleteResponse(status="deleted")


@router.post("/query", response_model=QueryResponse)
async def query(
    body: QueryRequest,
    ctx: AppContext = Depends(get_ctx),
) -> QueryResponse:
    results = await ctx.vector_service.query(
        tenant_id=body.tenant_id, text=body.text, vector=body.vector, filters=body.filters,
        top_k=body.top_k, hybrid=body.hybrid,
    )
    return QueryResponse(
        results=[ScoredResultSchema(id=r.id, score=r.score, payload=r.payload) for r in results]
    )


@router.post("/migrations", response_model=MigrationResponse, status_code=202)
async def start_migration(
    body: StartMigrationRequest,
    ctx: AppContext = Depends(get_ctx),
) -> MigrationResponse:
    record = await ctx.migration_manager.start(body.tenant_id, body.new_embedding_model)
    if record.status.value == "running":
        _run_migration_in_background(ctx, record.id)
    return MigrationResponse(migration_id=record.id, status=record.status.value)


@router.get("/migrations/{migration_id}", response_model=MigrationStatusResponse)
async def get_migration(
    migration_id: str,
    ctx: AppContext = Depends(get_ctx),
) -> MigrationStatusResponse:
    try:
        record = await ctx.migration_manager.get(migration_id)
    except MigrationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return MigrationStatusResponse(
        migration_id=record.id, status=record.status.value, progress=record.progress_ratio,
        points_total=record.points_total, points_migrated=record.points_migrated,
        created_at=record.created_at, completed_at=record.completed_at,
    )
