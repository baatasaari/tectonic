"""Request/response models for `/v1/intent-detection/*` (LLD §3.3)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class IntentDefinitionSchema(BaseModel):
    name: str
    description: str = ""
    examples: list[str] = []


class ClassifyRequest(BaseModel):
    text: str
    taxonomy_version: int | None = None


class DetectedIntentSchema(BaseModel):
    name: str
    confidence: float


class ClassifyResponse(BaseModel):
    intents: list[DetectedIntentSchema]
    fallback_used: bool
    taxonomy_version: int


class CreateTaxonomyRequest(BaseModel):
    tenant_id: str
    intents: list[IntentDefinitionSchema]


class TaxonomySummary(BaseModel):
    id: str
    version: int
    status: str


class ActivateTaxonomyResponse(BaseModel):
    status: str


class DriftReportSchema(BaseModel):
    id: str
    taxonomy_version: int
    drift_score: float
    flagged_intents: list[str]
    created_at: datetime
