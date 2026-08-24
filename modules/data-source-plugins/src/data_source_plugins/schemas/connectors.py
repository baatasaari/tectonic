"""Request/response models for `/v1/data-source-plugins/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CreateConnectorRequest(BaseModel):
    tenant_id: str
    source_type: str
    connection_config: dict[str, Any] = {}
    secrets_ref: str = ""
    sync_schedule: str | None = None


class ConnectorConfigSchema(BaseModel):
    id: str
    tenant_id: str
    source_type: str
    connection_config: dict[str, Any]
    sync_schedule: str | None
    status: str
    created_at: datetime


class SyncRunSchema(BaseModel):
    id: str
    connector_id: str
    status: str
    records_synced: int
    started_at: datetime
    completed_at: datetime | None


class QueryRequest(BaseModel):
    query: dict[str, Any] = {}


class QualityScoreSchema(BaseModel):
    id: str
    connector_id: str
    sync_run_id: str
    completeness_score: float
    freshness_score: float
    format_validity_score: float
    overall_score: float
    computed_at: datetime


class DriftIncidentSchema(BaseModel):
    id: str
    connector_id: str
    schema_diff: dict[str, Any]
    classification: str
    auto_adapted: bool
    resolved_by: str | None
    created_at: datetime


class DriftIncidentListResponse(BaseModel):
    items: list[DriftIncidentSchema]
    total: int
    limit: int
    offset: int
