"""SQLAlchemy-backed implementation of IntentRepository (LLD §3.1)."""
from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from intent_detection.core.domain import (
    ClassificationLogRecord,
    DetectedIntent,
    DriftReportRecord,
    IntentDefinition,
    IntentTaxonomyRecord,
    TaxonomyStatus,
)
from intent_detection.db import models


def _taxonomy_to_domain(m: models.IntentTaxonomy) -> IntentTaxonomyRecord:
    return IntentTaxonomyRecord(
        id=str(m.id), tenant_id=m.tenant_id, version=m.version,
        intents=[IntentDefinition(**i) for i in (m.intents or [])],
        status=TaxonomyStatus(m.status), created_at=m.created_at,
    )


def _log_to_domain(m: models.ClassificationLog) -> ClassificationLogRecord:
    return ClassificationLogRecord(
        id=str(m.id), tenant_id=m.tenant_id, input_hash=m.input_hash, taxonomy_version=m.taxonomy_version,
        intents_detected=[DetectedIntent(**i) for i in (m.intents_detected or [])],
        fallback_used=m.fallback_used, created_at=m.created_at,
    )


def _drift_to_domain(m: models.DriftReport) -> DriftReportRecord:
    return DriftReportRecord(
        id=str(m.id), tenant_id=m.tenant_id, taxonomy_version=m.taxonomy_version,
        drift_score=m.drift_score, flagged_intents=list(m.flagged_intents or []), created_at=m.created_at,
    )


class SQLAlchemyIntentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_taxonomy(self, record: IntentTaxonomyRecord) -> IntentTaxonomyRecord:
        m = models.IntentTaxonomy(
            id=record.id, tenant_id=record.tenant_id, version=record.version,
            intents=[asdict(i) for i in record.intents], status=record.status.value,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _taxonomy_to_domain(m)

    async def get_taxonomy(self, taxonomy_id: str) -> IntentTaxonomyRecord | None:
        m = await self.session.get(models.IntentTaxonomy, taxonomy_id)
        return _taxonomy_to_domain(m) if m else None

    async def get_active_taxonomy(self, tenant_id: str) -> IntentTaxonomyRecord | None:
        rows = await self.session.execute(
            select(models.IntentTaxonomy)
            .where(models.IntentTaxonomy.tenant_id == tenant_id, models.IntentTaxonomy.status == "active")
            .order_by(models.IntentTaxonomy.version.desc())
            .limit(1)
        )
        m = rows.scalars().first()
        return _taxonomy_to_domain(m) if m else None

    async def get_taxonomy_by_version(self, tenant_id: str, version: int) -> IntentTaxonomyRecord | None:
        rows = await self.session.execute(
            select(models.IntentTaxonomy).where(
                models.IntentTaxonomy.tenant_id == tenant_id, models.IntentTaxonomy.version == version
            )
        )
        m = rows.scalars().first()
        return _taxonomy_to_domain(m) if m else None

    async def activate_taxonomy(self, taxonomy_id: str) -> IntentTaxonomyRecord:
        m = await self.session.get(models.IntentTaxonomy, taxonomy_id)
        if m is None:
            raise LookupError(taxonomy_id)
        m.status = TaxonomyStatus.ACTIVE.value
        await self.session.commit()
        await self.session.refresh(m)
        return _taxonomy_to_domain(m)

    async def create_classification_log(self, record: ClassificationLogRecord) -> ClassificationLogRecord:
        m = models.ClassificationLog(
            id=record.id, tenant_id=record.tenant_id, input_hash=record.input_hash,
            taxonomy_version=record.taxonomy_version, intents_detected=[asdict(i) for i in record.intents_detected],
            fallback_used=record.fallback_used,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _log_to_domain(m)

    async def list_classification_logs(
        self, tenant_id: str, taxonomy_version: int | None = None
    ) -> list[ClassificationLogRecord]:
        stmt = select(models.ClassificationLog).where(models.ClassificationLog.tenant_id == tenant_id)
        if taxonomy_version is not None:
            stmt = stmt.where(models.ClassificationLog.taxonomy_version == taxonomy_version)
        rows = await self.session.execute(stmt)
        return [_log_to_domain(m) for m in rows.scalars().all()]

    async def create_drift_report(self, record: DriftReportRecord) -> DriftReportRecord:
        m = models.DriftReport(
            id=record.id, tenant_id=record.tenant_id, taxonomy_version=record.taxonomy_version,
            drift_score=record.drift_score, flagged_intents=record.flagged_intents,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _drift_to_domain(m)

    async def list_drift_reports(
        self, tenant_id: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[DriftReportRecord], int]:
        where_clause = models.DriftReport.tenant_id == tenant_id
        total_rows = await self.session.execute(
            select(func.count(models.DriftReport.id)).where(where_clause)
        )
        total = total_rows.scalar_one()

        rows = await self.session.execute(
            select(models.DriftReport)
            .where(where_clause)
            .order_by(models.DriftReport.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_drift_to_domain(m) for m in rows.scalars().all()], total
