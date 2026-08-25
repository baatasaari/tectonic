"""Request/response models for `/v1/promptops/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RegisterPromptVersionRequest(BaseModel):
    prompt_name: str
    version: str
    template: str


class PromptVersionSchema(BaseModel):
    id: str
    tenant_id: str
    prompt_name: str
    version: str
    template: str
    status: str
    parent_version_id: str | None
    promoted_pass_rate: float | None
    promoted_sample_size: int | None
    created_at: datetime
    updated_at: datetime


class PromptVersionListResponse(BaseModel):
    items: list[PromptVersionSchema]
    total: int
    limit: int
    offset: int


class StartABTestRequest(BaseModel):
    prompt_name: str
    version_a_id: str
    version_b_id: str


class ABTestSchema(BaseModel):
    id: str
    tenant_id: str
    prompt_name: str
    version_a_id: str
    version_b_id: str
    status: str
    winner_version_id: str | None
    p_value: float | None
    sample_size_a: int
    sample_size_b: int
    started_at: datetime
    concluded_at: datetime | None


class ABTestResultSchema(BaseModel):
    sample_size_a: int
    sample_size_b: int
    pass_rate_a: float | None
    pass_rate_b: float | None
    p_value: float | None
    significant: bool
    winner_version_id: str | None
    reason: str


class DriftCheckResultSchema(BaseModel):
    baseline_pass_rate: float | None
    current_pass_rate: float | None
    current_sample_size: int
    p_value: float | None
    drifted: bool
    reason: str
