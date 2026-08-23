"""`/v1/intent-detection/*` routes (LLD §3.3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from intent_detection.api.deps import build_classification_service, get_ctx, get_repository
from intent_detection.app_context import AppContext
from intent_detection.core.domain import (
    IntentDefinition,
    IntentTaxonomyRecord,
    NoActiveTaxonomyError,
    TaxonomyStatus,
    new_id,
)
from intent_detection.core.ports import IntentRepository
from intent_detection.schemas.intents import (
    ActivateTaxonomyResponse,
    ClassifyRequest,
    ClassifyResponse,
    CreateTaxonomyRequest,
    DetectedIntentSchema,
    DriftReportSchema,
    TaxonomySummary,
)

router = APIRouter(prefix="/v1/intent-detection", tags=["intent-detection"])


def _tenant_id(request: Request, ctx: AppContext) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


@router.post("/classify", response_model=ClassifyResponse)
async def classify(
    body: ClassifyRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: IntentRepository = Depends(get_repository),
) -> ClassifyResponse:
    tenant_id = _tenant_id(request, ctx)
    service = build_classification_service(ctx, repository)
    try:
        result = await service.classify(body.text, tenant_id, body.taxonomy_version)
    except NoActiveTaxonomyError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return ClassifyResponse(
        intents=[DetectedIntentSchema(name=i.name, confidence=i.confidence) for i in result.intents],
        fallback_used=result.fallback_used,
        taxonomy_version=result.taxonomy_version,
    )


@router.post("/taxonomies", response_model=TaxonomySummary, status_code=201)
async def create_taxonomy(
    body: CreateTaxonomyRequest,
    repository: IntentRepository = Depends(get_repository),
) -> TaxonomySummary:
    active = await repository.get_active_taxonomy(body.tenant_id)
    next_version = (active.version + 1) if active else 1

    record = IntentTaxonomyRecord(
        id=new_id(),
        tenant_id=body.tenant_id,
        version=next_version,
        intents=[IntentDefinition(name=i.name, description=i.description, examples=i.examples) for i in body.intents],
        status=TaxonomyStatus.DRAFT,
    )
    record = await repository.create_taxonomy(record)
    return TaxonomySummary(id=record.id, version=record.version, status=record.status.value)


@router.post("/taxonomies/{taxonomy_id}/activate", response_model=ActivateTaxonomyResponse)
async def activate_taxonomy(
    taxonomy_id: str,
    repository: IntentRepository = Depends(get_repository),
) -> ActivateTaxonomyResponse:
    existing = await repository.get_taxonomy(taxonomy_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="taxonomy not found")
    record = await repository.activate_taxonomy(taxonomy_id)
    return ActivateTaxonomyResponse(status=record.status.value)


@router.get("/drift-reports", response_model=list[DriftReportSchema])
async def list_drift_reports(
    tenant_id: str,
    date_range: str | None = Query(None, description="Reserved for future filtering; not yet enforced"),
    repository: IntentRepository = Depends(get_repository),
) -> list[DriftReportSchema]:
    reports = await repository.list_drift_reports(tenant_id)
    return [
        DriftReportSchema(
            id=r.id, taxonomy_version=r.taxonomy_version, drift_score=r.drift_score,
            flagged_intents=r.flagged_intents, created_at=r.created_at,
        )
        for r in reports
    ]
