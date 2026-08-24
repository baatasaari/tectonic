"""Request/response models for `/v1/regulatory-compliance/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CreateFrameworkProfileRequest(BaseModel):
    tenant_id: str
    framework_name: str
    version: str


class FrameworkProfileSchema(BaseModel):
    id: str
    tenant_id: str
    framework_name: str
    version: str
    enabled: bool
    created_at: datetime


class ControlMappingSchema(BaseModel):
    id: str
    control_name: str
    framework_name: str
    framework_version: str
    clause_references: list[str]
    mapping_rationale: str
    deprecated: bool


class ControlMappingListResponse(BaseModel):
    items: list[ControlMappingSchema]
    total: int
    limit: int
    offset: int


class ControlEventRequest(BaseModel):
    tenant_id: str
    control_name: str
    source_module: str
    evidence_ref: str


class MappingResultSchema(BaseModel):
    control_name: str
    framework_name: str
    clause_references: list[str]


class ControlEventResponse(BaseModel):
    id: str
    tenant_id: str
    control_name: str
    source_module: str
    evidence_ref: str
    occurred_at: datetime
    mappings: list[MappingResultSchema]


class CreateEvidencePackRequest(BaseModel):
    tenant_id: str
    framework_name: str
    date_range: dict | None = None


class EvidencePackSchema(BaseModel):
    id: str
    tenant_id: str
    framework_name: str
    status: str
    generated_at: datetime | None
    coverage_percentage: float
    document_ref: str | None
    document_format: str
    document_bytes_b64: str | None = None
    created_at: datetime


class CoverageResponse(BaseModel):
    tenant_id: str
    framework_name: str
    coverage_percentage: float
    gaps: list[str]


class PublishMappingsRequest(BaseModel):
    mappings: list[dict]
    deprecate_prior: bool = True


class PublishMappingsResponse(BaseModel):
    mappings_published: int
