"""Framework-agnostic domain objects (LLD §3 data model)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class BudgetPeriod(StrEnum):
    # The same two values LLM Gateway's own BudgetPeriod uses -- wire-compatible with
    # the real peer this module reads spend from, not a guessed vocabulary of its own.
    DAILY = "daily"
    MONTHLY = "monthly"


def period_window(period: BudgetPeriod, at: datetime) -> tuple[datetime, datetime]:
    """The [start, end) window a given instant falls within for this
    period type -- the boundary used both to sum this module's own usage
    events and to compute a forecast's "elapsed fraction of the period"."""
    if period == BudgetPeriod.DAILY:
        start = at.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)

    start = at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if at.month == 12:
        end = start.replace(year=at.year + 1, month=1)
    else:
        end = start.replace(month=at.month + 1)
    return start, end


class BudgetPolicyNotFoundError(Exception):
    def __init__(self, budget_policy_id: str) -> None:
        super().__init__(f"Budget policy not found: {budget_policy_id}")


@dataclass
class UsageEventRecord:
    id: str
    tenant_id: str
    source_module: str
    resource_type: str
    quantity: float
    unit_cost: float
    cost: float
    occurred_at: datetime = field(default_factory=now)


@dataclass
class BudgetPolicyRecord:
    id: str
    tenant_id: str
    period: BudgetPeriod
    limit_amount: float
    alert_threshold_pct: float = 0.8
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)


@dataclass
class OptimisationActionRecord:
    id: str
    tenant_id: str
    budget_policy_id: str
    action_type: str
    previous_value: float
    new_value: float
    reason: str
    taken_at: datetime = field(default_factory=now)


@dataclass
class CostReport:
    tenant_id: str
    period: BudgetPeriod
    llm_gateway_spend: float
    other_usage_cost: float
    total_cost: float
    forecast_amount: float | None
    budget_policy: BudgetPolicyRecord | None
    utilisation_ratio: float | None
    alert: bool
