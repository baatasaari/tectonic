"""`/v1/agent-marketplace/*` routes (LLD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from agent_marketplace.api.deps import (
    build_catalogue_service,
    build_catalogue_sync_service,
    build_governance_service,
    build_usage_tracking_service,
    get_ctx,
    get_repository,
    resolve_tenant_id,
)
from agent_marketplace.app_context import AppContext
from agent_marketplace.core.domain import (
    AgentCardNotFoundError,
    InvalidTransitionError,
    ListingNotFoundError,
    ListingStatus,
)
from agent_marketplace.core.ports import AgentMarketplaceRepository
from agent_marketplace.schemas.agent_marketplace import (
    ApproveListingRequest,
    ListingListResponse,
    ListingSchema,
    RecordUsageRequest,
    RejectListingRequest,
    ReuseMetricsSchema,
    SubmitListingRequest,
)

router = APIRouter(prefix="/v1/agent-marketplace", tags=["agent-marketplace"])


def _reject_null_byte_query(**params: str | None) -> None:
    """A raw `Query()` string parameter never runs through a Pydantic
    body field's own NUL-byte validator -- a real CI run of a sibling
    module's contract tier (ticket #82) surfaced this exact bug class
    on a raw query parameter, an `UntranslatableCharacterError` at the
    database instead of a clean 422. Applied at the top of every route
    below taking a free-text (non-enum) query parameter."""
    for name, value in params.items():
        if value is not None and "\x00" in value:
            raise HTTPException(status_code=422, detail=f"{name} must not contain a NUL byte")


def _listing_schema(listing) -> ListingSchema:
    return ListingSchema(
        id=listing.id, tenant_id=listing.tenant_id, agent_card_id=listing.agent_card_id, name=listing.name,
        description=listing.description, skills_snapshot=listing.skills_snapshot,
        trust_score_snapshot=listing.trust_score_snapshot, status=listing.status.value,
        submitted_by=listing.submitted_by, reviewed_by=listing.reviewed_by, reviewed_at=listing.reviewed_at,
        rejection_reason=listing.rejection_reason, reuse_count=listing.reuse_count,
        external_listing_enabled=listing.external_listing_enabled, created_at=listing.created_at,
        updated_at=listing.updated_at,
    )


@router.post("/listings", response_model=ListingSchema, status_code=201)
async def submit_listing(
    body: SubmitListingRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    ctx: AppContext = Depends(get_ctx),
    repository: AgentMarketplaceRepository = Depends(get_repository),
) -> ListingSchema:
    service = build_governance_service(repository, ctx)
    try:
        listing = await service.submit(
            tenant_id=tenant_id, agent_card_id=body.agent_card_id, submitted_by=body.submitted_by,
            external_listing_enabled=body.external_listing_enabled,
        )
    except AgentCardNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _listing_schema(listing)


@router.get("/listings", response_model=ListingListResponse)
async def search_listings(
    tenant_id: str | None = Query(None),
    status: ListingStatus | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: AgentMarketplaceRepository = Depends(get_repository),
) -> ListingListResponse:
    # `status` typed as ListingStatus | None: FastAPI/Pydantic validates and
    # coerces it itself, rejecting anything not a real ListingStatus value (a
    # NUL byte included) with a clean 422 -- this used to accept an arbitrary
    # str and call ListingStatus(status) by hand, which raised an unhandled
    # ValueError (500) for any non-member string (ticket #82).
    _reject_null_byte_query(tenant_id=tenant_id)
    service = build_catalogue_service(repository)
    parsed_status = status or ListingStatus.PUBLISHED
    listings, total = await service.search(tenant_id=tenant_id, status=parsed_status, limit=limit, offset=offset)
    return ListingListResponse(items=[_listing_schema(listing) for listing in listings], total=total, limit=limit, offset=offset)


@router.get("/listings/{listing_id}", response_model=ListingSchema)
async def get_listing(
    listing_id: str,
    repository: AgentMarketplaceRepository = Depends(get_repository),
) -> ListingSchema:
    listing = await repository.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail=str(ListingNotFoundError(listing_id)))
    return _listing_schema(listing)


@router.post("/listings/{listing_id}/approve", response_model=ListingSchema)
async def approve_listing(
    listing_id: str,
    body: ApproveListingRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: AgentMarketplaceRepository = Depends(get_repository),
) -> ListingSchema:
    service = build_governance_service(repository, ctx)
    try:
        listing = await service.approve(listing_id, reviewed_by=body.reviewed_by)
    except ListingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _listing_schema(listing)


@router.post("/listings/{listing_id}/reject", response_model=ListingSchema)
async def reject_listing(
    listing_id: str,
    body: RejectListingRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: AgentMarketplaceRepository = Depends(get_repository),
) -> ListingSchema:
    service = build_governance_service(repository, ctx)
    try:
        listing = await service.reject(listing_id, reviewed_by=body.reviewed_by, reason=body.reason)
    except ListingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _listing_schema(listing)


@router.post("/listings/{listing_id}/deprecate", response_model=ListingSchema)
async def deprecate_listing(
    listing_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: AgentMarketplaceRepository = Depends(get_repository),
) -> ListingSchema:
    service = build_governance_service(repository, ctx)
    try:
        listing = await service.deprecate(listing_id)
    except ListingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _listing_schema(listing)


@router.post("/listings/{listing_id}/sync", response_model=ListingSchema)
async def sync_listing(
    listing_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: AgentMarketplaceRepository = Depends(get_repository),
) -> ListingSchema:
    service = build_catalogue_sync_service(repository, ctx)
    try:
        listing = await service.sync(listing_id)
    except ListingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AgentCardNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _listing_schema(listing)


@router.post("/listings/{listing_id}/record-usage", response_model=ReuseMetricsSchema)
async def record_usage(
    listing_id: str,
    body: RecordUsageRequest,
    repository: AgentMarketplaceRepository = Depends(get_repository),
) -> ReuseMetricsSchema:
    service = build_usage_tracking_service(repository)
    try:
        metrics = await service.record_usage(listing_id, consumer_tenant_id=body.consumer_tenant_id)
    except ListingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ReuseMetricsSchema(reuse_count=metrics.reuse_count, distinct_consumer_tenants=metrics.distinct_consumer_tenants)


@router.get("/listings/{listing_id}/reuse-metrics", response_model=ReuseMetricsSchema)
async def reuse_metrics(
    listing_id: str,
    repository: AgentMarketplaceRepository = Depends(get_repository),
) -> ReuseMetricsSchema:
    service = build_usage_tracking_service(repository)
    try:
        metrics = await service.reuse_metrics(listing_id)
    except ListingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ReuseMetricsSchema(reuse_count=metrics.reuse_count, distinct_consumer_tenants=metrics.distinct_consumer_tenants)
