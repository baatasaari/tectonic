"""Request/response models for `/v1/guardrails/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CheckRequest(BaseModel):
    text: str
    stage: str
    policy_profile_id: str | None = None
    context: str | None = None  # see policy_engine.py's docstring for why this exists


class CheckResponse(BaseModel):
    decision: str
    violation_category: str | None
    redacted_text: str | None
    checks_run: list[str]


class CreatePolicyProfileRequest(BaseModel):
    tenant_id: str
    name: str = "default"
    enabled_checks: list[str] = ["pii_detection", "jailbreak_detection", "groundedness_check"]
    entity_types: list[str] = ["EMAIL", "PHONE_NUMBER", "PERSON", "CREDIT_CARD"]
    denied_topics: list[str] = []
    groundedness_threshold: float = 0.85


class PolicyProfileSchema(BaseModel):
    id: str
    tenant_id: str
    name: str
    enabled_checks: list[str]
    pii_entity_types: list[str]
    denied_topics: list[str]
    groundedness_threshold: float
    status: str
    created_at: datetime


class BypassIncidentSchema(BaseModel):
    id: str
    attack_pattern: str
    target_check: str
    severity: str
    resolved: bool


class RedTeamRunSchema(BaseModel):
    id: str
    attempts_generated: int
    successful_bypasses: int
    run_at: datetime
    bypass_incidents: list[BypassIncidentSchema] = []


class RedTeamRunListResponse(BaseModel):
    items: list[RedTeamRunSchema]
    total: int
    limit: int
    offset: int


class TriggerRedTeamRunResponse(BaseModel):
    run_id: str
