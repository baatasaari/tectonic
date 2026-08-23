"""Request/response models for `/v1/context-engineering/*` (LLD §3.3)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CandidateItemSchema(BaseModel):
    source: str
    content: str
    metadata: dict[str, Any] = {}


class AssembleRequest(BaseModel):
    candidate_items: list[CandidateItemSchema]
    token_budget: int | None = None
    task_type: str = "default"
    request_ref: str | None = None


class AssembleResponse(BaseModel):
    assembled_context: str
    tokens_used: int
    items_dropped_count: int
    items_included_count: int
    items_summarised_count: int


class CreateOntologyRequest(BaseModel):
    tenant_id: str
    roles: list[str] = []
    entity_types: list[str] = []
    policy_tags: list[str] = []


class OntologySummary(BaseModel):
    id: str
    version: int


class WeightsResponse(BaseModel):
    task_type: str
    feature_weights: dict[str, float]
