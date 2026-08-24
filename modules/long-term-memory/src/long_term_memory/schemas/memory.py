"""Request/response models for `/v1/long-term-memory/*` (LLD §3.1)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class StoreItemRequest(BaseModel):
    scope: str
    memory_type: str
    content: str
    visibility_policy_ref: str = ""


class MemoryItemSchema(BaseModel):
    id: str
    scope: str
    memory_type: str
    content: str
    visibility_policy_ref: str
    vector_ref: str | None
    graph_ref: str | None
    status: str
    relevance_score: float
    created_at: datetime
    last_accessed_at: datetime


class QueryRequest(BaseModel):
    scope: str
    query: str
    memory_types: list[str] | None = None
    top_k: int = 10
    requesting_agent: str | None = None


class RankedMemoryItemSchema(BaseModel):
    item: MemoryItemSchema
    score: float


class ReflectionEntrySchema(BaseModel):
    id: str
    agent_ref: str
    triggering_interaction_ref: str
    reflection_content: str
    applied: bool
    created_at: datetime


class ReflectionEntryListResponse(BaseModel):
    items: list[ReflectionEntrySchema]
    total: int
    limit: int
    offset: int


class GenerateReflectionRequest(BaseModel):
    agent_ref: str
    triggering_interaction_ref: str
    context: str


class ErasureRequest(BaseModel):
    subject_ref: str
    reason: str = ""
    requested_by: str = ""


class DeletionRecordSchema(BaseModel):
    id: str
    subject_ref: str
    status: str
    memory_items_deleted: list[str]
    deletion_proof_hash: str
    requested_by: str
    completed_at: datetime | None


class ConsolidationRunSchema(BaseModel):
    id: str
    items_merged_count: int
    items_decayed_count: int
    run_at: datetime
