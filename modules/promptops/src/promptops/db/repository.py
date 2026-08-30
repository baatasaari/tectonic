"""SQLAlchemy-backed implementation of PromptOpsRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from promptops.core.domain import (
    ABTestRecord,
    ABTestStatus,
    PromptVersionRecord,
    PromptVersionStatus,
)
from promptops.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _version_to_domain(m: models.PromptVersion) -> PromptVersionRecord:
    return PromptVersionRecord(
        id=str(m.id), tenant_id=m.tenant_id, prompt_name=m.prompt_name, version=m.version, template=m.template,
        status=PromptVersionStatus(m.status), parent_version_id=str(m.parent_version_id) if m.parent_version_id else None,
        promoted_pass_rate=m.promoted_pass_rate, promoted_sample_size=m.promoted_sample_size,
        created_at=_as_utc(m.created_at), updated_at=_as_utc(m.updated_at),
    )


def _ab_test_to_domain(m: models.ABTest) -> ABTestRecord:
    return ABTestRecord(
        id=str(m.id), tenant_id=m.tenant_id, prompt_name=m.prompt_name, version_a_id=str(m.version_a_id),
        version_b_id=str(m.version_b_id), status=ABTestStatus(m.status),
        winner_version_id=str(m.winner_version_id) if m.winner_version_id else None, p_value=m.p_value,
        sample_size_a=m.sample_size_a, sample_size_b=m.sample_size_b, started_at=_as_utc(m.started_at),
        concluded_at=_as_utc(m.concluded_at),
    )


class SQLAlchemyPromptOpsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_prompt_version(self, record: PromptVersionRecord) -> PromptVersionRecord:
        m = models.PromptVersion(
            id=record.id, tenant_id=record.tenant_id, prompt_name=record.prompt_name, version=record.version,
            template=record.template, status=record.status.value, parent_version_id=record.parent_version_id,
            promoted_pass_rate=record.promoted_pass_rate, promoted_sample_size=record.promoted_sample_size,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _version_to_domain(m)

    async def get_prompt_version(self, prompt_version_id: str) -> PromptVersionRecord | None:
        m = await self.session.get(models.PromptVersion, prompt_version_id)
        return _version_to_domain(m) if m else None

    async def update_prompt_version(self, record: PromptVersionRecord) -> PromptVersionRecord:
        m = await self.session.get(models.PromptVersion, record.id)
        m.status = record.status.value
        m.promoted_pass_rate = record.promoted_pass_rate
        m.promoted_sample_size = record.promoted_sample_size
        await self.session.commit()
        await self.session.refresh(m)
        return _version_to_domain(m)

    async def list_prompt_versions(
        self, *, tenant_id: str | None = None, prompt_name: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[PromptVersionRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.PromptVersion.tenant_id == tenant_id)
        if prompt_name is not None:
            filters.append(models.PromptVersion.prompt_name == prompt_name)

        count_stmt = select(func.count(models.PromptVersion.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.PromptVersion).where(*filters).order_by(models.PromptVersion.created_at.desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_version_to_domain(m) for m in rows.scalars().all()], total

    async def get_active_prompt_version(self, *, tenant_id: str, prompt_name: str) -> PromptVersionRecord | None:
        stmt = select(models.PromptVersion).where(
            models.PromptVersion.tenant_id == tenant_id, models.PromptVersion.prompt_name == prompt_name,
            models.PromptVersion.status == PromptVersionStatus.ACTIVE.value,
        )
        m = (await self.session.execute(stmt)).scalars().first()
        return _version_to_domain(m) if m else None

    async def create_ab_test(self, record: ABTestRecord) -> ABTestRecord:
        m = models.ABTest(
            id=record.id, tenant_id=record.tenant_id, prompt_name=record.prompt_name,
            version_a_id=record.version_a_id, version_b_id=record.version_b_id, status=record.status.value,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _ab_test_to_domain(m)

    async def get_ab_test(self, ab_test_id: str) -> ABTestRecord | None:
        m = await self.session.get(models.ABTest, ab_test_id)
        return _ab_test_to_domain(m) if m else None

    async def update_ab_test(self, record: ABTestRecord) -> ABTestRecord:
        m = await self.session.get(models.ABTest, record.id)
        m.status = record.status.value
        m.winner_version_id = record.winner_version_id
        m.p_value = record.p_value
        m.sample_size_a = record.sample_size_a
        m.sample_size_b = record.sample_size_b
        m.concluded_at = record.concluded_at
        await self.session.commit()
        await self.session.refresh(m)
        return _ab_test_to_domain(m)
