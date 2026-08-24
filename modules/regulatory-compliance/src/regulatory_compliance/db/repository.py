"""SQLAlchemy-backed implementation of RegulatoryComplianceRepository (LLD
§3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from regulatory_compliance.core.domain import (
    ControlImplementationEventRecord,
    ControlMappingRecord,
    EvidencePackRecord,
    EvidencePackStatus,
    FrameworkProfileRecord,
)
from regulatory_compliance.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _profile_to_domain(m: models.FrameworkProfile) -> FrameworkProfileRecord:
    return FrameworkProfileRecord(
        id=str(m.id), tenant_id=m.tenant_id, framework_name=m.framework_name, version=m.version,
        enabled=m.enabled, created_at=_as_utc(m.created_at),
    )


def _mapping_to_domain(m: models.ControlMapping) -> ControlMappingRecord:
    return ControlMappingRecord(
        id=str(m.id), control_name=m.control_name, framework_name=m.framework_name,
        framework_version=m.framework_version, clause_references=list(m.clause_references or []),
        mapping_rationale=m.mapping_rationale, deprecated=m.deprecated,
    )


def _event_to_domain(m: models.ControlImplementationEvent) -> ControlImplementationEventRecord:
    return ControlImplementationEventRecord(
        id=str(m.id), tenant_id=m.tenant_id, control_name=m.control_name, source_module=m.source_module,
        evidence_ref=m.evidence_ref, occurred_at=_as_utc(m.occurred_at),
    )


def _pack_to_domain(m: models.EvidencePack) -> EvidencePackRecord:
    return EvidencePackRecord(
        id=str(m.id), tenant_id=m.tenant_id, framework_name=m.framework_name,
        status=EvidencePackStatus(m.status), generated_at=_as_utc(m.generated_at),
        coverage_percentage=m.coverage_percentage, document_ref=m.document_ref,
        document_format=m.document_format, document_bytes_b64=m.document_bytes_b64,
        created_at=_as_utc(m.created_at),
    )


class SQLAlchemyRegulatoryComplianceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_framework_profile(self, record: FrameworkProfileRecord) -> FrameworkProfileRecord:
        m = models.FrameworkProfile(
            id=record.id, tenant_id=record.tenant_id, framework_name=record.framework_name, version=record.version,
            enabled=record.enabled,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _profile_to_domain(m)

    async def get_framework_profile(self, tenant_id: str, framework_name: str) -> FrameworkProfileRecord | None:
        rows = await self.session.execute(
            select(models.FrameworkProfile).where(
                models.FrameworkProfile.tenant_id == tenant_id, models.FrameworkProfile.framework_name == framework_name,
            )
        )
        m = rows.scalars().first()
        return _profile_to_domain(m) if m else None

    async def list_framework_profiles(self, tenant_id: str, *, enabled_only: bool = False) -> list[FrameworkProfileRecord]:
        stmt = select(models.FrameworkProfile).where(models.FrameworkProfile.tenant_id == tenant_id)
        if enabled_only:
            stmt = stmt.where(models.FrameworkProfile.enabled.is_(True))
        rows = await self.session.execute(stmt)
        return [_profile_to_domain(m) for m in rows.scalars().all()]

    async def upsert_control_mapping(self, record: ControlMappingRecord) -> ControlMappingRecord:
        rows = await self.session.execute(
            select(models.ControlMapping).where(
                models.ControlMapping.control_name == record.control_name,
                models.ControlMapping.framework_name == record.framework_name,
                models.ControlMapping.framework_version == record.framework_version,
                models.ControlMapping.deprecated.is_(False),
            )
        )
        existing = rows.scalars().first()
        if existing is not None:
            existing.clause_references = record.clause_references
            existing.mapping_rationale = record.mapping_rationale
            await self.session.commit()
            await self.session.refresh(existing)
            return _mapping_to_domain(existing)

        m = models.ControlMapping(
            id=record.id, control_name=record.control_name, framework_name=record.framework_name,
            framework_version=record.framework_version, clause_references=record.clause_references,
            mapping_rationale=record.mapping_rationale, deprecated=record.deprecated,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _mapping_to_domain(m)

    async def deprecate_control_mappings(self, control_name: str, framework_name: str, older_than_version: str) -> int:
        rows = await self.session.execute(
            select(models.ControlMapping).where(
                models.ControlMapping.control_name == control_name,
                models.ControlMapping.framework_name == framework_name,
                models.ControlMapping.framework_version != older_than_version,
                models.ControlMapping.deprecated.is_(False),
            )
        )
        count = 0
        for m in rows.scalars().all():
            m.deprecated = True
            count += 1
        await self.session.commit()
        return count

    async def list_control_mappings(
        self, *, control_name: str | None = None, framework_name: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[ControlMappingRecord], int]:
        filters = []
        if control_name is not None:
            filters.append(models.ControlMapping.control_name == control_name)
        if framework_name is not None:
            filters.append(models.ControlMapping.framework_name == framework_name)

        count_stmt = select(func.count(models.ControlMapping.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        # No natural timestamp column on this table (see models.ControlMapping) — order by
        # id ascending as a stable, deterministic last resort so limit/offset pagination is
        # meaningful (without an explicit order, row order across pages is undefined).
        stmt = (
            select(models.ControlMapping)
            .where(*filters)
            .order_by(models.ControlMapping.id.asc())
            .limit(limit)
            .offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_mapping_to_domain(m) for m in rows.scalars().all()], total

    async def create_control_event(self, record: ControlImplementationEventRecord) -> ControlImplementationEventRecord:
        m = models.ControlImplementationEvent(
            id=record.id, tenant_id=record.tenant_id, control_name=record.control_name,
            source_module=record.source_module, evidence_ref=record.evidence_ref,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _event_to_domain(m)

    async def list_control_events(self, tenant_id: str) -> list[ControlImplementationEventRecord]:
        rows = await self.session.execute(
            select(models.ControlImplementationEvent).where(models.ControlImplementationEvent.tenant_id == tenant_id)
        )
        return [_event_to_domain(m) for m in rows.scalars().all()]

    async def create_evidence_pack(self, record: EvidencePackRecord) -> EvidencePackRecord:
        m = models.EvidencePack(
            id=record.id, tenant_id=record.tenant_id, framework_name=record.framework_name,
            status=record.status.value, coverage_percentage=record.coverage_percentage,
            document_format=record.document_format,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _pack_to_domain(m)

    async def update_evidence_pack(self, record: EvidencePackRecord) -> EvidencePackRecord:
        m = await self.session.get(models.EvidencePack, record.id)
        if m is None:
            raise ValueError(f"evidence pack not found: {record.id}")
        m.status = record.status.value
        m.generated_at = record.generated_at
        m.coverage_percentage = record.coverage_percentage
        m.document_ref = record.document_ref
        m.document_format = record.document_format
        m.document_bytes_b64 = record.document_bytes_b64
        await self.session.commit()
        await self.session.refresh(m)
        return _pack_to_domain(m)

    async def get_evidence_pack(self, tenant_id: str, pack_id: str) -> EvidencePackRecord | None:
        m = await self.session.get(models.EvidencePack, pack_id)
        if m is None or m.tenant_id != tenant_id:
            return None
        return _pack_to_domain(m)
