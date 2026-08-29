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


class VirtualKeyListResponse(BaseModel):
    items: list[VirtualKeyResponse]
    total: int
    limit: int
    offset: int


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


class CreateProviderConfigRequest(BaseModel):
    """Ticket #82 (Phase 2 support-agent slice): before this, this module had
    no way at all -- through its own real API -- to provision a provider a
    tenant's completions could actually route to; `list_provider_configs`/
    `update_provider_config` both assumed a row already existed via some
    other, never-built mechanism (not even a data migration seeded one)."""

    provider_name: str
    endpoint: str
    priority: int = 0


class CreateBudgetPolicyRequest(BaseModel):
    tenant_id: str
    period: str
    limit_amount: float
    alert_threshold_pct: float = 0.8


class BudgetPolicyResponse(BaseModel):
    id: str
    tenant_id: str
    period: str
    limit_amount: float
    current_spend: float
    alert_threshold_pct: float
