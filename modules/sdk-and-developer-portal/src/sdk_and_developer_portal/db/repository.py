"""SQLAlchemy-backed implementation of PortalRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sdk_and_developer_portal.core.domain import (
    DeveloperAccountRecord,
    DeveloperStatus,
    ModuleCatalogEntryRecord,
    SdkPackageRecord,
)
from sdk_and_developer_portal.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _developer_to_domain(m: models.DeveloperAccount) -> DeveloperAccountRecord:
    return DeveloperAccountRecord(
        id=str(m.id), name=m.name, email=m.email, tenant_id=m.tenant_id, identity_id=m.identity_id,
        status=DeveloperStatus(m.status), created_at=_as_utc(m.created_at), updated_at=_as_utc(m.updated_at),
    )


def _catalog_entry_to_domain(m: models.ModuleCatalogEntry) -> ModuleCatalogEntryRecord:
    return ModuleCatalogEntryRecord(
        module_name=m.module_name, base_url=m.base_url, title=m.title, version=m.version,
        path_count=m.path_count, spec_json=dict(m.spec_json or {}), spec_hash=m.spec_hash,
        last_synced_at=_as_utc(m.last_synced_at),
    )


def _sdk_package_to_domain(m: models.SdkPackage) -> SdkPackageRecord:
    return SdkPackageRecord(
        id=str(m.id), module_name=m.module_name, language=m.language, version=m.version,
        source_code=m.source_code, spec_hash=m.spec_hash, generated_at=_as_utc(m.generated_at),
    )


class SQLAlchemyPortalRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_developer(self, record: DeveloperAccountRecord) -> DeveloperAccountRecord:
        m = models.DeveloperAccount(
            id=record.id, name=record.name, email=record.email, tenant_id=record.tenant_id,
            identity_id=record.identity_id, status=record.status.value,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _developer_to_domain(m)

    async def get_developer(self, developer_id: str) -> DeveloperAccountRecord | None:
        m = await self.session.get(models.DeveloperAccount, developer_id)
        return _developer_to_domain(m) if m else None

    async def update_developer(self, record: DeveloperAccountRecord) -> DeveloperAccountRecord:
        m = await self.session.get(models.DeveloperAccount, record.id)
        m.status = record.status.value
        await self.session.commit()
        await self.session.refresh(m)
        return _developer_to_domain(m)

    async def list_developers(
        self, *, status: DeveloperStatus | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[DeveloperAccountRecord], int]:
        filters = []
        if status is not None:
            filters.append(models.DeveloperAccount.status == status.value)

        count_stmt = select(func.count(models.DeveloperAccount.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.DeveloperAccount).where(*filters).order_by(models.DeveloperAccount.created_at.desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_developer_to_domain(m) for m in rows.scalars().all()], total

    async def count_developers(self, *, status: DeveloperStatus | None = None) -> int:
        filters = []
        if status is not None:
            filters.append(models.DeveloperAccount.status == status.value)
        stmt = select(func.count(models.DeveloperAccount.id)).where(*filters)
        return (await self.session.execute(stmt)).scalar_one()

    async def list_all_developers(self) -> list[DeveloperAccountRecord]:
        rows = await self.session.execute(select(models.DeveloperAccount))
        return [_developer_to_domain(m) for m in rows.scalars().all()]

    async def upsert_catalog_entry(self, record: ModuleCatalogEntryRecord) -> ModuleCatalogEntryRecord:
        m = await self.session.get(models.ModuleCatalogEntry, record.module_name)
        if m is None:
            m = models.ModuleCatalogEntry(module_name=record.module_name)
            self.session.add(m)
        m.base_url = record.base_url
        m.title = record.title
        m.version = record.version
        m.path_count = record.path_count
        m.spec_json = record.spec_json
        m.spec_hash = record.spec_hash
        await self.session.commit()
        await self.session.refresh(m)
        return _catalog_entry_to_domain(m)

    async def get_catalog_entry(self, module_name: str) -> ModuleCatalogEntryRecord | None:
        m = await self.session.get(models.ModuleCatalogEntry, module_name)
        return _catalog_entry_to_domain(m) if m else None

    async def list_catalog_entries(
        self, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ModuleCatalogEntryRecord], int]:
        count_stmt = select(func.count(models.ModuleCatalogEntry.module_name))
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.ModuleCatalogEntry).order_by(models.ModuleCatalogEntry.module_name)
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_catalog_entry_to_domain(m) for m in rows.scalars().all()], total

    async def create_sdk_package(self, record: SdkPackageRecord) -> SdkPackageRecord:
        m = models.SdkPackage(
            id=record.id, module_name=record.module_name, language=record.language, version=record.version,
            source_code=record.source_code, spec_hash=record.spec_hash,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _sdk_package_to_domain(m)

    async def get_sdk_package(self, package_id: str) -> SdkPackageRecord | None:
        m = await self.session.get(models.SdkPackage, package_id)
        return _sdk_package_to_domain(m) if m else None

    async def get_latest_sdk_package(self, *, module_name: str, language: str) -> SdkPackageRecord | None:
        stmt = (
            select(models.SdkPackage)
            .where(models.SdkPackage.module_name == module_name, models.SdkPackage.language == language)
            .order_by(models.SdkPackage.version.desc()).limit(1)
        )
        m = (await self.session.execute(stmt)).scalar_one_or_none()
        return _sdk_package_to_domain(m) if m else None

    async def list_sdk_packages(
        self, *, module_name: str | None = None, language: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[SdkPackageRecord], int]:
        filters = []
        if module_name is not None:
            filters.append(models.SdkPackage.module_name == module_name)
        if language is not None:
            filters.append(models.SdkPackage.language == language)

        count_stmt = select(func.count(models.SdkPackage.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.SdkPackage).where(*filters).order_by(models.SdkPackage.generated_at.desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_sdk_package_to_domain(m) for m in rows.scalars().all()], total
