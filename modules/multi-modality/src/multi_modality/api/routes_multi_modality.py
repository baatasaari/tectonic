"""`/v1/multi-modality/*` routes (LLD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from multi_modality.api.deps import (
    build_extraction_service,
    get_ctx,
    get_repository,
    resolve_tenant_id,
)
from multi_modality.app_context import AppContext
from multi_modality.core.domain import ExtractionNotFoundError, Modality
from multi_modality.core.ports import MultiModalityRepository
from multi_modality.schemas.multi_modality import (
    ExtractionListResponse,
    ExtractionSchema,
    ExtractRequest,
)

router = APIRouter(prefix="/v1/multi-modality", tags=["multi-modality"])


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


def _extraction_schema(extraction) -> ExtractionSchema:
    return ExtractionSchema(
        id=extraction.id, tenant_id=extraction.tenant_id, modality=extraction.modality.value,
        raw_content=extraction.raw_content, extracted_content=extraction.extracted_content,
        grounding_context=extraction.grounding_context, groundedness_decision=extraction.groundedness_decision.value,
        groundedness_violation_category=extraction.groundedness_violation_category, latency_ms=extraction.latency_ms,
        created_at=extraction.created_at,
    )


@router.post("/extractions", response_model=ExtractionSchema, status_code=201)
async def extract(
    body: ExtractRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    ctx: AppContext = Depends(get_ctx),
    repository: MultiModalityRepository = Depends(get_repository),
) -> ExtractionSchema:
    service = build_extraction_service(repository, ctx)
    try:
        modality = Modality(body.modality)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"unknown modality: {body.modality}") from exc

    extraction = await service.extract(
        tenant_id=tenant_id, modality=modality, raw_content=body.raw_content, grounding_context=body.grounding_context,
    )
    return _extraction_schema(extraction)


@router.get("/extractions", response_model=ExtractionListResponse)
async def list_extractions(
    tenant_id: str | None = Query(None),
    modality: Modality | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000_000),
    repository: MultiModalityRepository = Depends(get_repository),
) -> ExtractionListResponse:
    _reject_null_byte_query(tenant_id=tenant_id)
    extractions, total = await repository.list_extractions(
        tenant_id=tenant_id, modality=modality, limit=limit, offset=offset,
    )
    return ExtractionListResponse(
        items=[_extraction_schema(e) for e in extractions], total=total, limit=limit, offset=offset,
    )


@router.get("/extractions/{extraction_id}", response_model=ExtractionSchema)
async def get_extraction(
    extraction_id: str,
    repository: MultiModalityRepository = Depends(get_repository),
) -> ExtractionSchema:
    extraction = await repository.get_extraction(extraction_id)
    if extraction is None:
        raise HTTPException(status_code=404, detail=str(ExtractionNotFoundError(extraction_id)))
    return _extraction_schema(extraction)
