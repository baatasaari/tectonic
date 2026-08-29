"""SQLAlchemy-backed implementation of GatewayRepository (LLD §3.1)."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llm_gateway.core.domain import (
    BudgetPeriod,
    BudgetPolicyRecord,
    ProviderConfigRecord,
    RequestLogRecord,
    VirtualKeyRecord,
    VirtualKeyStatus,
)
from llm_gateway.db import models


def _is_valid_uuid(value: str) -> bool:
    """`id` columns are Postgres `UUID`; a caller-supplied `str` that
    isn't a syntactically valid UUID by definition names no row, but
    handing it to `asyncpg` regardless raises an unhandled
    `ValueError`/`DataError` deep in the driver instead of a clean
    `None`/404 path (found by this module's own OpenAPI contract-test
    tier -- see Billing and Metering's `db/repository.py` for the
    original instance of this exact fix)."""
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _vk_to_domain(m: models.VirtualKey) -> VirtualKeyRecord:
    return VirtualKeyRecord(
        id=str(m.id),
        tenant_id=m.tenant_id,
        provider_scope=list(m.provider_scope or []),
        budget_policy_ref=m.budget_policy_ref,
        status=VirtualKeyStatus(m.status),
        created_at=m.created_at,
    )


def _budget_to_domain(m: models.BudgetPolicy) -> BudgetPolicyRecord:
    return BudgetPolicyRecord(
        id=str(m.id),
        tenant_id=m.tenant_id,
        period=BudgetPeriod(m.period),
        limit_amount=m.limit_amount,
        current_spend=m.current_spend,
        alert_threshold_pct=m.alert_threshold_pct,
    )


def _provider_to_domain(m: models.ProviderConfig) -> ProviderConfigRecord:
    return ProviderConfigRecord(
        id=str(m.id),
        provider_name=m.provider_name,
        endpoint=m.endpoint,
        priority=m.priority,
        health_status=m.health_status,
        deprecation_notices=list(m.deprecation_notices or []),
    )


class SQLAlchemyGatewayRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_virtual_key(self, record: VirtualKeyRecord) -> VirtualKeyRecord:
        m = models.VirtualKey(
            id=record.id, tenant_id=record.tenant_id, provider_scope=record.provider_scope,
            budget_policy_ref=record.budget_policy_ref, status=record.status.value,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _vk_to_domain(m)

    async def get_virtual_key(self, virtual_key_id: str) -> VirtualKeyRecord | None:
        if not _is_valid_uuid(virtual_key_id):
            return None
        m = await self.session.get(models.VirtualKey, virtual_key_id)
        return _vk_to_domain(m) if m else None

    async def list_virtual_keys(
        self, tenant_id: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[VirtualKeyRecord], int]:
        where_clause = models.VirtualKey.tenant_id == tenant_id
        total_rows = await self.session.execute(select(func.count(models.VirtualKey.id)).where(where_clause))
        total = total_rows.scalar_one()

        rows = await self.session.execute(
            select(models.VirtualKey)
            .where(where_clause)
            .order_by(models.VirtualKey.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_vk_to_domain(m) for m in rows.scalars().all()], total

    async def get_budget_policy(self, budget_policy_id: str) -> BudgetPolicyRecord | None:
        if not _is_valid_uuid(budget_policy_id):
            return None
        m = await self.session.get(models.BudgetPolicy, budget_policy_id)
        return _budget_to_domain(m) if m else None

    async def create_budget_policy(self, record: BudgetPolicyRecord) -> BudgetPolicyRecord:
        m = models.BudgetPolicy(
            id=record.id, tenant_id=record.tenant_id, period=record.period.value,
            limit_amount=record.limit_amount, current_spend=record.current_spend,
            alert_threshold_pct=record.alert_threshold_pct,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _budget_to_domain(m)

    async def update_budget_spend(self, budget_policy_id: str, new_spend: float) -> BudgetPolicyRecord:
        m = await self.session.get(models.BudgetPolicy, budget_policy_id)
        if m is None:
            raise LookupError(budget_policy_id)
        m.current_spend = new_spend
        await self.session.commit()
        await self.session.refresh(m)
        return _budget_to_domain(m)

    async def create_request_log(self, record: RequestLogRecord) -> RequestLogRecord:
        m = models.RequestLog(
            id=record.id, tenant_id=record.tenant_id, virtual_key_id=record.virtual_key_id,
            provider=record.provider, model=record.model, input_tokens=record.input_tokens,
            output_tokens=record.output_tokens, cost=record.cost, cache_hit=record.cache_hit,
            latency_ms=record.latency_ms,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return record

    async def list_provider_configs(self) -> list[ProviderConfigRecord]:
        rows = await self.session.execute(select(models.ProviderConfig))
        return [_provider_to_domain(m) for m in rows.scalars().all()]

    async def update_provider_config(self, record: ProviderConfigRecord) -> ProviderConfigRecord:
        m = await self.session.get(models.ProviderConfig, record.id)
        if m is None:
            raise LookupError(record.id)
        m.health_status = record.health_status
        m.priority = record.priority
        m.deprecation_notices = record.deprecation_notices
        await self.session.commit()
        await self.session.refresh(m)
        return _provider_to_domain(m)
