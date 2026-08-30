"""SQLAlchemy-backed implementation of DeploymentStrategyRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from deployment_strategy.core.domain import DeploymentRecord, DeploymentStage
from deployment_strategy.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _deployment_to_domain(m: models.Deployment) -> DeploymentRecord:
    return DeploymentRecord(
        id=str(m.id), tenant_id=m.tenant_id, service_name=m.service_name, build_ref=m.build_ref, target=m.target,
        canary_percentage=m.canary_percentage, budget_policy_id=str(m.budget_policy_id) if m.budget_policy_id else None,
        stage=DeploymentStage(m.stage), started_at=_as_utc(m.started_at), promoted_at=_as_utc(m.promoted_at),
        rolled_back_at=_as_utc(m.rolled_back_at), rollback_reason=m.rollback_reason,
        created_at=_as_utc(m.created_at), updated_at=_as_utc(m.updated_at),
    )


class SQLAlchemyDeploymentStrategyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_deployment(self, record: DeploymentRecord) -> DeploymentRecord:
        m = models.Deployment(
            id=record.id, tenant_id=record.tenant_id, service_name=record.service_name, build_ref=record.build_ref,
            target=record.target, canary_percentage=record.canary_percentage, budget_policy_id=record.budget_policy_id,
            stage=record.stage.value,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _deployment_to_domain(m)

    async def get_deployment(self, deployment_id: str) -> DeploymentRecord | None:
        m = await self.session.get(models.Deployment, deployment_id)
        return _deployment_to_domain(m) if m else None

    async def update_deployment(self, record: DeploymentRecord) -> DeploymentRecord:
        m = await self.session.get(models.Deployment, record.id)
        m.stage = record.stage.value
        m.promoted_at = record.promoted_at
        m.rolled_back_at = record.rolled_back_at
        m.rollback_reason = record.rollback_reason
        await self.session.commit()
        await self.session.refresh(m)
        return _deployment_to_domain(m)

    async def get_active_deployment(self, *, tenant_id: str, service_name: str, target: str) -> DeploymentRecord | None:
        stmt = select(models.Deployment).where(
            models.Deployment.tenant_id == tenant_id, models.Deployment.service_name == service_name,
            models.Deployment.target == target, models.Deployment.stage == DeploymentStage.ACTIVE.value,
        )
        m = (await self.session.execute(stmt)).scalars().first()
        return _deployment_to_domain(m) if m else None

    async def list_deployments(
        self, *, tenant_id: str | None = None, service_name: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[DeploymentRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.Deployment.tenant_id == tenant_id)
        if service_name is not None:
            filters.append(models.Deployment.service_name == service_name)

        count_stmt = select(func.count(models.Deployment.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.Deployment).where(*filters).order_by(models.Deployment.created_at.desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_deployment_to_domain(m) for m in rows.scalars().all()], total
