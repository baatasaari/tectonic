"""Request/response models for `/v1/agent-cards/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AgentSkillSchema(BaseModel):
    id: str
    name: str
    description: str = ""


class RegisterCardRequest(BaseModel):
    agent_ref: str
    name: str
    description: str = ""
    url: str
    skills: list[AgentSkillSchema] = []


class UpdateCardRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    url: str | None = None
    skills: list[AgentSkillSchema] | None = None


class AgentCardSchema(BaseModel):
    id: str
    tenant_id: str
    agent_ref: str
    name: str
    description: str
    url: str
    skills: list[AgentSkillSchema]
    trust_score: float | None
    trust_score_computed_at: datetime | None
    last_verified_at: datetime
    is_stale: bool
    created_at: datetime
    updated_at: datetime


class AgentCardListResponse(BaseModel):
    items: list[AgentCardSchema]
    total: int
    limit: int
    offset: int


class TrustScoreBreakdownSchema(BaseModel):
    performance_score: float | None
    compliance_score: float | None
    trust_score: float | None
    computed_at: datetime
