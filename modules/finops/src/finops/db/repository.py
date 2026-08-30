"""SQLAlchemy-backed implementation of FinOpsRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finops.core.domain import (
    BudgetPeriod,
    BudgetPolicyRecord,
    OptimisationActionRecord,
    UsageEventRecord,
)
from finops.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _policy_to_domain(m: models.BudgetPolicy) -> BudgetPolicyRecord:
    return BudgetPolicyRecord(
        id=str(m.id), tenant_id=m.tenant_id, period=BudgetPeriod(m.period), limit_amount=m.limit_amount,
        alert_threshold_pct=m.alert_threshold_pct, created_at=_as_utc(m.created_at), updated_at=_as_utc(m.updated_at),
    )


def _action_to_domain(m: models.OptimisationAction) -> OptimisationActionRecord:
    return OptimisationActionRecord(
        id=str(m.id), tenant_id=m.tenant_id, budget_policy_id=str(m.budget_policy_id), action_type=m.action_type,
        previous_value=m.previous_value, new_value=m.new_value, reason=m.reason, taken_at=_as_utc(m.taken_at),
    )


class SQLAlchemyFinOpsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_usage_event(self, record: UsageEventRecord) -> UsageEventRecord:
        m = models.UsageEvent(
            id=record.id, tenant_id=record.tenant_id, source_module=record.source_module,
            resource_type=record.resource_type, quantity=record.quantity, unit_cost=record.unit_cost,
            cost=record.cost, occurred_at=record.occurred_at,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return record

    async def sum_usage_cost(self, *, tenant_id: str, start: datetime, end: datetime) -> float:
        stmt = select(func.coalesce(func.sum(models.UsageEvent.cost), 0.0)).where(
            models.UsageEvent.tenant_id == tenant_id,
            models.UsageEvent.occurred_at >= start,
            models.UsageEvent.occurred_at < end,
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def create_budget_policy(self, record: BudgetPolicyRecord) -> BudgetPolicyRecord:
        m = models.BudgetPolicy(
            id=record.id, tenant_id=record.tenant_id, period=record.period.value, limit_amount=record.limit_amount,
            alert_threshold_pct=record.alert_threshold_pct,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _policy_to_domain(m)

    async def get_budget_policy(self, budget_policy_id: str) -> BudgetPolicyRecord | None:
        m = await self.session.get(models.BudgetPolicy, budget_policy_id)
        return _policy_to_domain(m) if m else None

    async def update_budget_policy(self, record: BudgetPolicyRecord) -> BudgetPolicyRecord:
        m = await self.session.get(models.BudgetPolicy, record.id)
        m.alert_threshold_pct = record.alert_threshold_pct
        m.limit_amount = record.limit_amount
        await self.session.commit()
        await self.session.refresh(m)
        return _policy_to_domain(m)

    async def create_optimisation_action(self, record: OptimisationActionRecord) -> OptimisationActionRecord:
        m = models.OptimisationAction(
            id=record.id, tenant_id=record.tenant_id, budget_policy_id=record.budget_policy_id,
            action_type=record.action_type, previous_value=record.previous_value, new_value=record.new_value,
            reason=record.reason,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _action_to_domain(m)

    async def list_optimisation_actions(
        self, *, budget_policy_id: str, limit: int = 50, offset: int = 0,
    ) -> tuple[list[OptimisationActionRecord], int]:
        count_stmt = select(func.count(models.OptimisationAction.id)).where(
            models.OptimisationAction.budget_policy_id == budget_policy_id
        )
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.OptimisationAction)
            .where(models.OptimisationAction.budget_policy_id == budget_policy_id)
            .order_by(models.OptimisationAction.taken_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_action_to_domain(m) for m in rows.scalars().all()], total
