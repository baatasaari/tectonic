"""`/v1/data-source-plugins/*` routes (LLD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from data_source_plugins.api.deps import build_sync_service, get_ctx, get_repository
from data_source_plugins.app_context import AppContext
from data_source_plugins.core.domain import ConnectorConfigRecord, ConnectorNotFoundError, new_id
from data_source_plugins.core.ports import ConnectorRepository
from data_source_plugins.schemas.connectors import (
    ConnectorConfigSchema,
    CreateConnectorRequest,
    DriftIncidentSchema,
    QualityScoreSchema,
    QueryRequest,
    SyncRunSchema,
)

router = APIRouter(prefix="/v1/data-source-plugins", tags=["data-source-plugins"])


def _connector_schema(record: ConnectorConfigRecord) -> ConnectorConfigSchema:
    return ConnectorConfigSchema(
        id=record.id, tenant_id=record.tenant_id, source_type=record.source_type,
        connection_config=record.connection_config, sync_schedule=record.sync_schedule,
        status=record.status.value, created_at=record.created_at,
    )


@router.post("/connectors", response_model=ConnectorConfigSchema, status_code=201)
async def create_connector(
    body: CreateConnectorRequest,
    repository: ConnectorRepository = Depends(get_repository),
) -> ConnectorConfigSchema:
    record = ConnectorConfigRecord(
        id=new_id(), tenant_id=body.tenant_id, source_type=body.source_type,
        connection_config=body.connection_config, secrets_ref=body.secrets_ref, sync_schedule=body.sync_schedule,
    )
    record = await repository.create_connector(record)
    return _connector_schema(record)


@router.get("/connectors/{connector_id}", response_model=ConnectorConfigSchema)
async def get_connector(
    connector_id: str,
    repository: ConnectorRepository = Depends(get_repository),
) -> ConnectorConfigSchema:
    record = await repository.get_connector(connector_id)
    if record is None:
        raise HTTPException(status_code=404, detail="connector not found")
    return _connector_schema(record)


@router.post("/connectors/{connector_id}/sync", response_model=SyncRunSchema)
async def trigger_sync(
    connector_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: ConnectorRepository = Depends(get_repository),
) -> SyncRunSchema:
    service = build_sync_service(ctx, repository)
    try:
        outcome = await service.sync(connector_id)
    except ConnectorNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    run = outcome.sync_run
    return SyncRunSchema(
        id=run.id, connector_id=run.connector_id, status=run.status.value,
        records_synced=run.records_synced, started_at=run.started_at, completed_at=run.completed_at,
    )


@router.post("/connectors/{connector_id}/query")
async def query_connector(
    connector_id: str,
    body: QueryRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: ConnectorRepository = Depends(get_repository),
) -> list[dict]:
    service = build_sync_service(ctx, repository)
    try:
        return await service.query(connector_id, body.query)
    except ConnectorNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/connectors/{connector_id}/quality", response_model=QualityScoreSchema)
async def get_quality(
    connector_id: str,
    repository: ConnectorRepository = Depends(get_repository),
) -> QualityScoreSchema:
    score = await repository.get_latest_quality_score(connector_id)
    if score is None:
        raise HTTPException(status_code=404, detail="no quality score recorded yet")
    return QualityScoreSchema(
        id=score.id, connector_id=score.connector_id, sync_run_id=score.sync_run_id,
        completeness_score=score.completeness_score, freshness_score=score.freshness_score,
        format_validity_score=score.format_validity_score, overall_score=score.overall_score,
        computed_at=score.computed_at,
    )


@router.get("/connectors/{connector_id}/drift-incidents", response_model=list[DriftIncidentSchema])
async def list_drift_incidents(
    connector_id: str,
    repository: ConnectorRepository = Depends(get_repository),
) -> list[DriftIncidentSchema]:
    incidents = await repository.list_drift_incidents(connector_id)
    return [
        DriftIncidentSchema(
            id=i.id, connector_id=i.connector_id, schema_diff=i.schema_diff, classification=i.classification.value,
            auto_adapted=i.auto_adapted, resolved_by=i.resolved_by, created_at=i.created_at,
        )
        for i in incidents
    ]
