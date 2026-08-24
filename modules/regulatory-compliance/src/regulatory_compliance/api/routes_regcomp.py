"""`/v1/regulatory-compliance/*` routes (LLD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from regulatory_compliance.api.deps import (
    build_coverage_calculator,
    build_crosswalk_engine,
    build_feed_manager,
    get_ctx,
    get_repository,
)
from regulatory_compliance.app_context import AppContext
from regulatory_compliance.core.domain import (
    EvidencePackNotFoundError,
    EvidencePackRecord,
    EvidencePackStatus,
    FrameworkProfileRecord,
    new_id,
)
from regulatory_compliance.core.ports import RegulatoryComplianceRepository
from regulatory_compliance.schemas.regcomp import (
    ControlEventRequest,
    ControlEventResponse,
    ControlMappingListResponse,
    ControlMappingSchema,
    CoverageResponse,
    CreateEvidencePackRequest,
    CreateFrameworkProfileRequest,
    EvidencePackSchema,
    FrameworkProfileSchema,
    MappingResultSchema,
    PublishMappingsRequest,
    PublishMappingsResponse,
)

router = APIRouter(prefix="/v1/regulatory-compliance", tags=["regulatory-compliance"])


def _profile_schema(p: FrameworkProfileRecord) -> FrameworkProfileSchema:
    return FrameworkProfileSchema(
        id=p.id, tenant_id=p.tenant_id, framework_name=p.framework_name, version=p.version, enabled=p.enabled,
        created_at=p.created_at,
    )


def _pack_schema(p: EvidencePackRecord, *, include_document: bool = False) -> EvidencePackSchema:
    return EvidencePackSchema(
        id=p.id, tenant_id=p.tenant_id, framework_name=p.framework_name, status=p.status.value,
        generated_at=p.generated_at, coverage_percentage=p.coverage_percentage, document_ref=p.document_ref,
        document_format=p.document_format, document_bytes_b64=p.document_bytes_b64 if include_document else None,
        created_at=p.created_at, attempts=p.attempts, last_error=p.last_error,
    )


@router.post("/framework-profiles", response_model=FrameworkProfileSchema, status_code=201)
async def create_framework_profile(
    body: CreateFrameworkProfileRequest,
    repository: RegulatoryComplianceRepository = Depends(get_repository),
) -> FrameworkProfileSchema:
    record = FrameworkProfileRecord(
        id=new_id(), tenant_id=body.tenant_id, framework_name=body.framework_name, version=body.version,
    )
    record = await repository.create_framework_profile(record)
    return _profile_schema(record)


@router.get("/mappings", response_model=ControlMappingListResponse)
async def list_mappings(
    control_name: str | None = Query(None),
    framework_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: RegulatoryComplianceRepository = Depends(get_repository),
) -> ControlMappingListResponse:
    mappings, total = await repository.list_control_mappings(
        control_name=control_name, framework_name=framework_name, limit=limit, offset=offset,
    )
    return ControlMappingListResponse(
        items=[
            ControlMappingSchema(
                id=m.id, control_name=m.control_name, framework_name=m.framework_name,
                framework_version=m.framework_version, clause_references=m.clause_references,
                mapping_rationale=m.mapping_rationale, deprecated=m.deprecated,
            )
            for m in mappings
        ],
        total=total, limit=limit, offset=offset,
    )


@router.post("/mappings/publish", response_model=PublishMappingsResponse)
async def publish_mappings(
    body: PublishMappingsRequest,
    repository: RegulatoryComplianceRepository = Depends(get_repository),
) -> PublishMappingsResponse:
    """The Regulatory Feed Manager's publish endpoint (LLD §Level 3 "Sequence: regulatory
    feed update") — an operator posts a new mapping table version here."""
    feed_manager = build_feed_manager(repository)
    count = await feed_manager.publish(body.mappings, deprecate_prior=body.deprecate_prior)
    return PublishMappingsResponse(mappings_published=count)


@router.post("/control-events", response_model=ControlEventResponse, status_code=201)
async def record_control_event(
    body: ControlEventRequest,
    repository: RegulatoryComplianceRepository = Depends(get_repository),
) -> ControlEventResponse:
    """Direct ingestion of a control-implementation event. The LLD's own diagram has these
    events arrive via Auditability (Human Oversight/Guardrails/Workflow Engine publish to
    Auditability, which forwards here) — since Auditability (Module 20) isn't built yet in
    this platform, source modules post here directly. Wiring a real Auditability-event
    consumer becomes a drop-in replacement for this endpoint once Module 20 exists."""
    engine = build_crosswalk_engine(repository)
    mappings = await engine.map_control(body.tenant_id, body.control_name, body.source_module, body.evidence_ref)
    events = await repository.list_control_events(body.tenant_id)
    event = next(e for e in reversed(events) if e.control_name == body.control_name and e.evidence_ref == body.evidence_ref)
    return ControlEventResponse(
        id=event.id, tenant_id=event.tenant_id, control_name=event.control_name, source_module=event.source_module,
        evidence_ref=event.evidence_ref, occurred_at=event.occurred_at,
        mappings=[
            MappingResultSchema(control_name=m.control_name, framework_name=m.framework_name, clause_references=m.clause_references)
            for m in mappings
        ],
    )


@router.get("/coverage", response_model=CoverageResponse)
async def coverage(
    tenant_id: str = Query(...),
    framework_name: str = Query(...),
    repository: RegulatoryComplianceRepository = Depends(get_repository),
) -> CoverageResponse:
    calculator = build_coverage_calculator(repository)
    pct, gaps = await calculator.coverage(tenant_id, framework_name)
    return CoverageResponse(tenant_id=tenant_id, framework_name=framework_name, coverage_percentage=pct, gaps=gaps)


@router.post("/evidence-packs", response_model=EvidencePackSchema, status_code=202)
async def create_evidence_pack(
    body: CreateEvidencePackRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: RegulatoryComplianceRepository = Depends(get_repository),
) -> EvidencePackSchema:
    """Enqueues generation and returns immediately — the record itself, at
    status=generating, IS the queue entry. `EvidencePackWorker` (started in main.py's
    lifespan) picks it up via a durable Postgres SELECT FOR UPDATE SKIP LOCKED poll
    loop, not an in-process FastAPI BackgroundTasks job, so a pod restart between this
    202 response and the job completing no longer loses the work: the pack stays
    claimable by any worker instance until it actually finishes."""
    record = EvidencePackRecord(
        id=new_id(), tenant_id=body.tenant_id, framework_name=body.framework_name, status=EvidencePackStatus.GENERATING,
        document_format=ctx.settings.evidence.output_format,
    )
    record = await repository.create_evidence_pack(record)
    return _pack_schema(record)


@router.get("/evidence-packs/{pack_id}", response_model=EvidencePackSchema)
async def get_evidence_pack(
    pack_id: str,
    tenant_id: str = Query(...),
    include_document: bool = Query(False),
    repository: RegulatoryComplianceRepository = Depends(get_repository),
) -> EvidencePackSchema:
    record = await repository.get_evidence_pack(tenant_id, pack_id)
    if record is None:
        raise HTTPException(status_code=404, detail=str(EvidencePackNotFoundError(pack_id)))
    return _pack_schema(record, include_document=include_document)
