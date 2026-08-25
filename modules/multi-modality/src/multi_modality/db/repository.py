"""SQLAlchemy-backed implementation of MultiModalityRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from multi_modality.core.domain import ExtractionRecord, GroundednessDecision, Modality
from multi_modality.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _extraction_to_domain(m: models.Extraction) -> ExtractionRecord:
    return ExtractionRecord(
        id=str(m.id), tenant_id=m.tenant_id, modality=Modality(m.modality), raw_content=m.raw_content,
        extracted_content=m.extracted_content, grounding_context=m.grounding_context,
        groundedness_decision=GroundednessDecision(m.groundedness_decision),
        groundedness_violation_category=m.groundedness_violation_category, latency_ms=m.latency_ms,
        created_at=_as_utc(m.created_at),
    )


class SQLAlchemyMultiModalityRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_extraction(self, record: ExtractionRecord) -> ExtractionRecord:
        m = models.Extraction(
            id=record.id, tenant_id=record.tenant_id, modality=record.modality.value, raw_content=record.raw_content,
            extracted_content=record.extracted_content, grounding_context=record.grounding_context,
            groundedness_decision=record.groundedness_decision.value,
            groundedness_violation_category=record.groundedness_violation_category, latency_ms=record.latency_ms,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _extraction_to_domain(m)

    async def get_extraction(self, extraction_id: str) -> ExtractionRecord | None:
        m = await self.session.get(models.Extraction, extraction_id)
        return _extraction_to_domain(m) if m else None

    async def list_extractions(
        self, *, tenant_id: str | None = None, modality: Modality | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ExtractionRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.Extraction.tenant_id == tenant_id)
        if modality is not None:
            filters.append(models.Extraction.modality == modality.value)

        count_stmt = select(func.count(models.Extraction.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.Extraction).where(*filters).order_by(models.Extraction.created_at.desc())
            .limit(limit).offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_extraction_to_domain(m) for m in rows.scalars().all()], total
