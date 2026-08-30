"""SQLAlchemy-backed implementation of LLMOpsRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llmops.core.domain import (
    DeploymentRecord,
    DeploymentStage,
    ModelVersionRecord,
    ModelVersionStatus,
)
from llmops.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _version_to_domain(m: models.ModelVersion) -> ModelVersionRecord:
    return ModelVersionRecord(
        id=str(m.id), tenant_id=m.tenant_id, model_name=m.model_name, version=m.version, artifact_ref=m.artifact_ref,
        status=ModelVersionStatus(m.status), created_at=_as_utc(m.created_at),
    )


def _deployment_to_domain(m: models.Deployment) -> DeploymentRecord:
    return DeploymentRecord(
        id=str(m.id), tenant_id=m.tenant_id, model_version_id=str(m.model_version_id), model_name=m.model_name,
        target=m.target, canary_percentage=m.canary_percentage, stage=DeploymentStage(m.stage),
        started_at=_as_utc(m.started_at), promoted_at=_as_utc(m.promoted_at), rolled_back_at=_as_utc(m.rolled_back_at),
        rollback_reason=m.rollback_reason, created_at=_as_utc(m.created_at), updated_at=_as_utc(m.updated_at),
    )


class SQLAlchemyLLMOpsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_model_version(self, record: ModelVersionRecord) -> ModelVersionRecord:
        m = models.ModelVersion(
            id=record.id, tenant_id=record.tenant_id, model_name=record.model_name, version=record.version,
            artifact_ref=record.artifact_ref, status=record.status.value,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _version_to_domain(m)

    async def get_model_version(self, model_version_id: str) -> ModelVersionRecord | None:
        m = await self.session.get(models.ModelVersion, model_version_id)
        return _version_to_domain(m) if m else None

    async def update_model_version(self, record: ModelVersionRecord) -> ModelVersionRecord:
        m = await self.session.get(models.ModelVersion, record.id)
        m.status = record.status.value
        await self.session.commit()
        await self.session.refresh(m)
        return _version_to_domain(m)

    async def list_model_versions(
        self, *, tenant_id: str | None = None, model_name: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ModelVersionRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.ModelVersion.tenant_id == tenant_id)
        if model_name is not None:
            filters.append(models.ModelVersion.model_name == model_name)

        count_stmt = select(func.count(models.ModelVersion.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.ModelVersion).where(*filters).order_by(models.ModelVersion.created_at.desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_version_to_domain(m) for m in rows.scalars().all()], total

    async def create_deployment(self, record: DeploymentRecord) -> DeploymentRecord:
        m = models.Deployment(
            id=record.id, tenant_id=record.tenant_id, model_version_id=record.model_version_id,
            model_name=record.model_name, target=record.target, canary_percentage=record.canary_percentage,
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

    async def get_active_deployment(self, *, tenant_id: str, model_name: str, target: str) -> DeploymentRecord | None:
        stmt = select(models.Deployment).where(
            models.Deployment.tenant_id == tenant_id, models.Deployment.model_name == model_name,
            models.Deployment.target == target, models.Deployment.stage == DeploymentStage.ACTIVE.value,
        )
        m = (await self.session.execute(stmt)).scalars().first()
        return _deployment_to_domain(m) if m else None
