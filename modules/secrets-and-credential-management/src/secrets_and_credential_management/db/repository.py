"""SQLAlchemy-backed implementation of SecretsRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from secrets_and_credential_management.core.domain import (
    SecretAccessRecord,
    SecretRecord,
    SecretStatus,
    SecretVersionRecord,
)
from secrets_and_credential_management.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _secret_to_domain(m: models.Secret) -> SecretRecord:
    return SecretRecord(
        id=str(m.id), tenant_id=m.tenant_id, namespace=m.namespace, key_name=m.key_name,
        status=SecretStatus(m.status), rotation_interval_days=m.rotation_interval_days,
        last_rotated_at=_as_utc(m.last_rotated_at), next_rotation_due_at=_as_utc(m.next_rotation_due_at),
        current_version=m.current_version, created_at=_as_utc(m.created_at), updated_at=_as_utc(m.updated_at),
    )


def _version_to_domain(m: models.SecretVersion) -> SecretVersionRecord:
    return SecretVersionRecord(
        id=str(m.id), secret_id=m.secret_id, version=m.version, ciphertext=m.ciphertext,
        wrapped_data_key=m.wrapped_data_key, created_at=_as_utc(m.created_at),
    )


def _access_to_domain(m: models.SecretAccess) -> SecretAccessRecord:
    return SecretAccessRecord(
        id=str(m.id), secret_id=m.secret_id, tenant_id=m.tenant_id, allowed=m.allowed, reason=m.reason,
        accessed_at=_as_utc(m.accessed_at),
    )


class SQLAlchemySecretsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_secret(self, record: SecretRecord) -> SecretRecord:
        m = models.Secret(
            id=record.id, tenant_id=record.tenant_id, namespace=record.namespace, key_name=record.key_name,
            status=record.status.value, rotation_interval_days=record.rotation_interval_days,
            last_rotated_at=record.last_rotated_at, next_rotation_due_at=record.next_rotation_due_at,
            current_version=record.current_version,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _secret_to_domain(m)

    async def get_secret(self, secret_id: str) -> SecretRecord | None:
        m = await self.session.get(models.Secret, secret_id)
        return _secret_to_domain(m) if m else None

    async def update_secret(self, record: SecretRecord) -> SecretRecord:
        m = await self.session.get(models.Secret, record.id)
        m.status = record.status.value
        m.rotation_interval_days = record.rotation_interval_days
        m.last_rotated_at = record.last_rotated_at
        m.next_rotation_due_at = record.next_rotation_due_at
        m.current_version = record.current_version
        await self.session.commit()
        await self.session.refresh(m)
        return _secret_to_domain(m)

    async def list_secrets(
        self, *, tenant_id: str | None = None, namespace: str | None = None, status: SecretStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[SecretRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.Secret.tenant_id == tenant_id)
        if namespace is not None:
            filters.append(models.Secret.namespace == namespace)
        if status is not None:
            filters.append(models.Secret.status == status.value)

        count_stmt = select(func.count(models.Secret.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.Secret).where(*filters).order_by(models.Secret.created_at.desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_secret_to_domain(m) for m in rows.scalars().all()], total

    async def list_due_for_rotation(
        self, *, tenant_id: str | None = None, at: datetime, limit: int = 50, offset: int = 0,
    ) -> tuple[list[SecretRecord], int]:
        filters = [models.Secret.status == SecretStatus.ACTIVE.value, models.Secret.next_rotation_due_at <= at]
        if tenant_id is not None:
            filters.append(models.Secret.tenant_id == tenant_id)

        count_stmt = select(func.count(models.Secret.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.Secret).where(*filters).order_by(models.Secret.next_rotation_due_at.asc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_secret_to_domain(m) for m in rows.scalars().all()], total

    async def create_version(self, record: SecretVersionRecord) -> SecretVersionRecord:
        m = models.SecretVersion(
            id=record.id, secret_id=record.secret_id, version=record.version, ciphertext=record.ciphertext,
            wrapped_data_key=record.wrapped_data_key,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _version_to_domain(m)

    async def get_latest_version(self, secret_id: str) -> SecretVersionRecord | None:
        stmt = (
            select(models.SecretVersion).where(models.SecretVersion.secret_id == secret_id)
            .order_by(models.SecretVersion.version.desc()).limit(1)
        )
        m = (await self.session.execute(stmt)).scalar_one_or_none()
        return _version_to_domain(m) if m else None

    async def create_access_record(self, record: SecretAccessRecord) -> SecretAccessRecord:
        m = models.SecretAccess(
            id=record.id, secret_id=record.secret_id, tenant_id=record.tenant_id, allowed=record.allowed,
            reason=record.reason,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _access_to_domain(m)

    async def list_access_records(
        self, *, secret_id: str, limit: int = 50, offset: int = 0,
    ) -> tuple[list[SecretAccessRecord], int]:
        filters = [models.SecretAccess.secret_id == secret_id]
        count_stmt = select(func.count(models.SecretAccess.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.SecretAccess).where(*filters).order_by(models.SecretAccess.accessed_at.desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_access_to_domain(m) for m in rows.scalars().all()], total

    async def count_active_and_overdue(self, *, tenant_id: str | None, at: datetime) -> tuple[int, int]:
        active_filters = [models.Secret.status == SecretStatus.ACTIVE.value]
        if tenant_id is not None:
            active_filters.append(models.Secret.tenant_id == tenant_id)

        total_active = (await self.session.execute(
            select(func.count(models.Secret.id)).where(*active_filters),
        )).scalar_one()
        overdue = (await self.session.execute(
            select(func.count(models.Secret.id)).where(*active_filters, models.Secret.next_rotation_due_at <= at),
        )).scalar_one()
        return total_active, overdue
