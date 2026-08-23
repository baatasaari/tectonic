"""Admin-scoped request/response models (LLD §3.3)."""
from __future__ import annotations

from pydantic import BaseModel


class CreateVirtualKeyRequest(BaseModel):
    tenant_id: str
    provider_scope: list[str] = []
    budget_policy_ref: str


class VirtualKeyResponse(BaseModel):
    id: str
    tenant_id: str
    provider_scope: list[str]
    budget_policy_ref: str
    status: str


class BudgetStatusResponse(BaseModel):
    id: str
    tenant_id: str
    period: str
    limit_amount: float
    current_spend: float
    utilisation_ratio: float
    alert_threshold_pct: float
    alert: bool


class ProviderStatusResponse(BaseModel):
    provider_name: str
    priority: int
    health_status: str
    deprecation_notices: list[dict]
