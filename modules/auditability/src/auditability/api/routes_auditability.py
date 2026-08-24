"""`/v1/auditability/*` routes (LLD §3)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from auditability.api.deps import (
    build_ingestion_service,
    build_nl_query_translator,
    get_ctx,
    get_repository,
)
from auditability.app_context import AppContext
from auditability.core.chain_verifier import verify_chain
from auditability.core.domain import (
    AuditEventFilter,
    AuditPackNotFoundError,
    AuditPackRecord,
    AuditPackStatus,
    InvalidNLQueryFilterError,
    new_id,
)
from auditability.core.ports import AuditabilityRepository
from auditability.schemas.auditability import (
    AuditEventListResponse,
    AuditEventSchema,
    AuditPackSchema,
    ChainVerificationResponse,
    CreateAuditPackRequest,
    NLQueryFilterEcho,
    NLQueryRequest,
    NLQueryResponse,
)
from auditability.security.jwt_auth import caller_service_name

router = APIRouter(prefix="/v1/auditability", tags=["auditability"])


def _event_schema(e) -> AuditEventSchema:
    return AuditEventSchema(
        id=e.id, tenant_id=e.tenant_id, source_module=e.source_module, event_type=e.event_type,
        payload=e.payload, sequence_number=e.sequence_number, entry_hash=e.entry_hash, prev_hash=e.prev_hash,
        occurred_at=e.occurred_at,
    )


def _pack_schema(p: AuditPackRecord, *, include_document: bool = False) -> AuditPackSchema:
    return AuditPackSchema(
        id=p.id, tenant_id=p.tenant_id, status=p.status.value, event_count=p.event_count,
        chain_valid=p.chain_valid, generated_at=p.generated_at, document_ref=p.document_ref,
        document_format=p.document_format, document_bytes_b64=p.document_bytes_b64 if include_document else None,
        created_at=p.created_at, attempts=p.attempts, last_error=p.last_error,
    )


@router.post("/events", response_model=AuditEventSchema, status_code=201)
async def ingest_event(
    request: Request,
    body: dict[str, Any] = Body(...),
    repository: AuditabilityRepository = Depends(get_repository),
) -> AuditEventSchema:
    tenant_id = body.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id is required")

    # source_module comes from the verified inbound JWT's iss claim, never from the
    # request body -- see security/jwt_auth.py's module docstring.
    source_module = caller_service_name(request)
    service = build_ingestion_service(repository)
    event = await service.ingest(tenant_id=tenant_id, source_module=source_module, payload=body)
    return _event_schema(event)


@router.get("/events", response_model=AuditEventListResponse)
async def list_events(
    tenant_id: str = Query(...),
    event_type: str | None = Query(None),
    source_module: str | None = Query(None),
    control_name: str | None = Query(None),
    occurred_after: datetime | None = Query(None),
    occurred_before: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: AuditabilityRepository = Depends(get_repository),
) -> AuditEventListResponse:
    event_filter = AuditEventFilter(
        tenant_id=tenant_id, event_type=event_type, source_module=source_module, control_name=control_name,
        occurred_after=occurred_after, occurred_before=occurred_before, limit=limit, offset=offset,
    )
    events, total = await repository.list_events(event_filter)
    return AuditEventListResponse(items=[_event_schema(e) for e in events], total=total, limit=limit, offset=offset)


@router.get("/events/verify-chain", response_model=ChainVerificationResponse)
async def verify_chain_route(
    tenant_id: str = Query(...),
    repository: AuditabilityRepository = Depends(get_repository),
) -> ChainVerificationResponse:
    events = await repository.list_events_for_chain(tenant_id)
    result = verify_chain(events)
    return ChainVerificationResponse(
        tenant_id=tenant_id, valid=result.valid, verified_count=result.verified_count,
        break_at_sequence=result.break_at_sequence,
    )


@router.post("/audit-packs", response_model=AuditPackSchema, status_code=202)
async def create_audit_pack(
    body: CreateAuditPackRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: AuditabilityRepository = Depends(get_repository),
) -> AuditPackSchema:
    """Enqueues generation and returns immediately -- the record itself, at
    status=generating, IS the queue entry. `AuditPackWorker` (started in main.py's
    lifespan) picks it up via a durable Postgres SELECT FOR UPDATE SKIP LOCKED poll
    loop, the same design Module 17 already proved for its own evidence packs."""
    record = AuditPackRecord(
        id=new_id(), tenant_id=body.tenant_id, status=AuditPackStatus.GENERATING,
        filter_event_type=body.event_type, filter_source_module=body.source_module,
        filter_control_name=body.control_name, filter_occurred_after=body.occurred_after,
        filter_occurred_before=body.occurred_before, document_format=ctx.settings.audit_pack.output_format,
    )
    record = await repository.create_audit_pack(record)
    return _pack_schema(record)


@router.get("/audit-packs/{pack_id}", response_model=AuditPackSchema)
async def get_audit_pack(
    pack_id: str,
    tenant_id: str = Query(...),
    include_document: bool = Query(False),
    repository: AuditabilityRepository = Depends(get_repository),
) -> AuditPackSchema:
    record = await repository.get_audit_pack(tenant_id, pack_id)
    if record is None:
        raise HTTPException(status_code=404, detail=str(AuditPackNotFoundError(pack_id)))
    return _pack_schema(record, include_document=include_document)


@router.post("/query", response_model=NLQueryResponse)
async def nl_query(
    body: NLQueryRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: AuditabilityRepository = Depends(get_repository),
) -> NLQueryResponse:
    if not ctx.settings.nl_query.enabled:
        raise HTTPException(status_code=400, detail="natural-language query is disabled on this deployment")

    translator = build_nl_query_translator(ctx)
    try:
        event_filter = await translator.translate(body.question, body.tenant_id)
    except InvalidNLQueryFilterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    events, total = await repository.list_events(event_filter)
    return NLQueryResponse(
        filter_used=NLQueryFilterEcho(
            event_type=event_filter.event_type, source_module=event_filter.source_module,
            control_name=event_filter.control_name, occurred_after=event_filter.occurred_after,
            occurred_before=event_filter.occurred_before,
        ),
        results=AuditEventListResponse(
            items=[_event_schema(e) for e in events], total=total,
            limit=event_filter.limit, offset=event_filter.offset,
        ),
    )
