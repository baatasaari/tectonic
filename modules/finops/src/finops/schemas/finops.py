"""Request/response models for `/v1/finops/*` (LLD §3)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from finops.core.domain import BudgetPeriod


class ReportUsageEventRequest(BaseModel):
    source_module: str
    resource_type: str
    quantity: float
    unit_cost: float


class UsageEventSchema(BaseModel):
    id: str
    tenant_id: str
    source_module: str
    resource_type: str
    quantity: float
    unit_cost: float
    cost: float
    occurred_at: datetime


class CreateBudgetPolicyRequest(BaseModel):
    # BudgetPeriod, not str: FastAPI/Pydantic then validates and coerces this
    # itself, rejecting anything not a real member with a clean 422 -- the
    # route used to accept an arbitrary str here and call BudgetPeriod(...) by
    # hand, which raised an unhandled ValueError (500) for any non-member
    # string (ticket #82, the same fix as this module's own GET
    # /cost-reports/{tenant_id}?period=... query parameter).
    period: BudgetPeriod
    limit_amount: float
    alert_threshold_pct: float = 0.8


class BudgetPolicySchema(BaseModel):
    id: str
    tenant_id: str
    period: str
    limit_amount: float
    alert_threshold_pct: float
    created_at: datetime
    updated_at: datetime


class CostReportSchema(BaseModel):
    tenant_id: str
    period: str
    llm_gateway_spend: float
    other_usage_cost: float
    total_cost: float
    forecast_amount: float | None
    budget_policy: BudgetPolicySchema | None
    utilisation_ratio: float | None
    alert: bool


class OptimisationActionSchema(BaseModel):
    id: str
    tenant_id: str
    budget_policy_id: str
    action_type: str
    previous_value: float
    new_value: float
    reason: str
    taken_at: datetime


class OptimisationActionListResponse(BaseModel):
    items: list[OptimisationActionSchema]
    total: int
    limit: int
    offset: int
