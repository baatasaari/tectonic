"""`/v1/human-oversight/*` routes (LLD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from human_oversight.api.deps import (
    build_decision_capture,
    build_notification_dispatcher,
    build_queue_manager,
    get_ctx,
    get_repository,
)
from human_oversight.app_context import AppContext
from human_oversight.core.domain import (
    RequestNotClaimableError,
    RequestNotDecidableError,
    RequestNotFoundError,
)
from human_oversight.core.ports import HumanOversightRepository
from human_oversight.schemas.oversight import (
    ClaimRequest,
    ClaimResponse,
    CreateRequestRequest,
    DecideRequest,
    DecisionSchema,
    OversightRequestDetailSchema,
    OversightRequestListResponse,
    OversightRequestSchema,
)

router = APIRouter(prefix="/v1/human-oversight", tags=["human-oversight"])


def _request_schema(r) -> OversightRequestSchema:
    return OversightRequestSchema(
        id=r.id, tenant_id=r.tenant_id, requesting_module=r.requesting_module, requesting_ref=r.requesting_ref,
        context=r.context, priority=r.priority, status=r.status.value, claimed_by=r.claimed_by,
        created_at=r.created_at, expires_at=r.expires_at,
    )


def _decision_schema(d) -> DecisionSchema:
    return DecisionSchema(
        id=d.id, request_id=d.request_id, decision=d.decision.value, decided_by=d.decided_by,
        decision_reason=d.decision_reason, decided_at=d.decided_at,
    )


@router.post("/requests", response_model=OversightRequestSchema, status_code=201)
async def create_request(
    body: CreateRequestRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: HumanOversightRepository = Depends(get_repository),
) -> OversightRequestSchema:
    queue_manager = build_queue_manager(ctx, repository)
    request = await queue_manager.enqueue(
        tenant_id=body.tenant_id, requesting_module=body.requesting_module, requesting_ref=body.requesting_ref,
        context=body.context, priority=body.priority, timeout_seconds=body.timeout_seconds,
    )

    dispatcher = build_notification_dispatcher(ctx)
    await dispatcher.dispatch(repository, request, ctx.settings.notification.channels)

    return _request_schema(request)


@router.post("/requests/{request_id}/claim", response_model=ClaimResponse)
async def claim_request(
    request_id: str,
    body: ClaimRequest,
    tenant_id: str = Query(...),
    ctx: AppContext = Depends(get_ctx),
    repository: HumanOversightRepository = Depends(get_repository),
) -> ClaimResponse:
    queue_manager = build_queue_manager(ctx, repository)
    try:
        request = await queue_manager.claim(tenant_id, request_id, body.claimed_by)
    except RequestNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RequestNotClaimableError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return ClaimResponse(status=request.status.value)


@router.post("/requests/{request_id}/decide", response_model=DecisionSchema)
async def decide_request(
    request_id: str,
    body: DecideRequest,
    tenant_id: str = Query(...),
    ctx: AppContext = Depends(get_ctx),
    repository: HumanOversightRepository = Depends(get_repository),
) -> DecisionSchema:
    capture = build_decision_capture(ctx, repository)
    try:
        decision = await capture.capture(
            tenant_id, request_id, decision=body.decision, decided_by=body.decided_by,
            decision_reason=body.decision_reason, override_details=body.override_details,
        )
    except RequestNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RequestNotDecidableError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return _decision_schema(decision)


@router.get("/requests", response_model=OversightRequestListResponse)
async def list_requests(
    tenant_id: str = Query(...),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: HumanOversightRepository = Depends(get_repository),
) -> OversightRequestListResponse:
    requests, total = await repository.list_requests(tenant_id, status, limit=limit, offset=offset)
    return OversightRequestListResponse(
        items=[_request_schema(r) for r in requests], total=total, limit=limit, offset=offset,
    )


@router.get("/requests/{request_id}", response_model=OversightRequestDetailSchema)
async def get_request(
    request_id: str,
    tenant_id: str = Query(...),
    repository: HumanOversightRepository = Depends(get_repository),
) -> OversightRequestDetailSchema:
    request = await repository.get_request(tenant_id, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="request not found")
    decision = await repository.get_decision_for_request(request_id)
    return OversightRequestDetailSchema(
        **_request_schema(request).model_dump(), decision=_decision_schema(decision) if decision else None,
    )
