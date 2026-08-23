"""Request/response models for `/v1/agentic-rag/*` (LLD §3.3)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RetrieveRequest(BaseModel):
    query: str
    scope: list[str] = []
    max_hops: int | None = None
    groundedness_threshold: float | None = None


class RetrievedItemSchema(BaseModel):
    content: str
    source: str
    source_document: str
    version: str
    location: str
    retrieval_score: float


class RetrieveResponse(BaseModel):
    synthesized_context: str
    groundedness_score: float
    hop_count: int
    outcome: str
    provenance_chain: list[dict]


class HopSummary(BaseModel):
    hop_number: int
    reformulated_query: str | None
    groundedness_score: float
    item_count: int


class RequestDetail(BaseModel):
    id: str
    tenant_id: str
    query: str
    scope: list[str]
    max_hops: int
    groundedness_threshold: float
    created_at: datetime
    hops: list[HopSummary]
    result: RetrieveResponse | None = None
