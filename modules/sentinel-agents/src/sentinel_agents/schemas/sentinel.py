"""Request/response models for `/v1/sentinel-agents/*` (LLD §3, plus the
event-ingestion addition — see the module README)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class IngestEventRequest(BaseModel):
    tenant_id: str
    agent_ref: str
    action_type: str
    value: float
    instance_id: str | None = None
    timestamp: datetime | None = None


class IngestEventResponse(BaseModel):
    alert_id: str | None
    alert_type: str | None
    severity: str | None


class AlertSchema(BaseModel):
    id: str
    alert_type: str
    agent_refs: list[str]
    severity: str
    description: str
    status: str
    detected_at: datetime


class BaselineSchema(BaseModel):
    agent_ref: str
    action_type: str
    mean: float
    variance: float
    sample_count: int
    last_updated_at: datetime


class ConfigureRequest(BaseModel):
    tenant_id: str
    autonomy_level_per_severity: dict[str, str] | None = None
    intervention_policy: dict | None = None


class ConfigureResponse(BaseModel):
    status: str
