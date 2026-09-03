"""Request/response models for `/v1/long-term-memory/*` (LLD §3.1)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from long_term_memory.core.domain import ConsentBasis


def _reject_null_byte(value: str) -> str:
    """Postgres's `text`/`varchar` columns are UTF-8 and reject the NUL
    byte outright -- a value `str` is happy to hold but the database is
    not. Applied to the memory-governance fields added alongside this
    validator (`purpose`, consent/legal-hold request fields), matching
    the `_reject_null_byte` pattern ticket #82 already established
    elsewhere on this platform's other request schemas."""
    if "\x00" in value:
        raise ValueError("must not contain a NUL byte (unsupported by Postgres's text encoding)")
    return value


class StoreItemRequest(BaseModel):
    scope: str
    memory_type: str
    content: str
    visibility_policy_ref: str = ""
    # Memory governance: what this item was collected for -- see
    # core/domain.py's MemoryItemRecord.purpose docstring. Optional and
    # unenforced at store time by design; MemoryService.query is where
    # it pairs with an active ConsentRecord to actually gate retrieval.
    purpose: str = ""

    @field_validator("purpose")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)


class MemoryItemSchema(BaseModel):
    id: str
    scope: str
    memory_type: str
    content: str
    visibility_policy_ref: str
    purpose: str
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


class GrantConsentRequest(BaseModel):
    # `basis` is typed as the real ConsentBasis enum, not a bare `str` hand-
    # converted at the route -- ticket #82's own sibling bug class (an
    # invalid value raising an unhandled ValueError/500 instead of a clean
    # 422), learned the hard way on Identity and Access's own
    # RegisterIdentityRequest.type this same session and applied directly
    # here rather than repeating it.
    scope: str
    purpose: str
    basis: ConsentBasis
    granted_by: str = ""

    @field_validator("scope", "purpose", "granted_by")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)


class ConsentRecordSchema(BaseModel):
    id: str
    scope: str
    purpose: str
    basis: str
    granted_by: str
    granted_at: datetime
    revoked_at: datetime | None


class ConsentRecordListResponse(BaseModel):
    items: list[ConsentRecordSchema]


class PlaceLegalHoldRequest(BaseModel):
    scope: str
    reason: str
    placed_by: str = ""

    @field_validator("scope", "reason", "placed_by")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)


class LegalHoldSchema(BaseModel):
    id: str
    scope: str
    reason: str
    placed_by: str
    placed_at: datetime
    released_at: datetime | None


class LegalHoldListResponse(BaseModel):
    items: list[LegalHoldSchema]
