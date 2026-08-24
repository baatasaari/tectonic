"""SQLAlchemy-backed implementation of AgentMarketplaceRepository (LLD §3)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_marketplace.core.domain import ListingRecord, ListingStatus, UsageEventRecord
from agent_marketplace.db import models


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _to_domain(m: models.AgentMarketplaceListing) -> ListingRecord:
    return ListingRecord(
        id=str(m.id), tenant_id=m.tenant_id, agent_card_id=m.agent_card_id, name=m.name, description=m.description,
        skills_snapshot=list(m.skills_snapshot or []), trust_score_snapshot=m.trust_score_snapshot,
        status=ListingStatus(m.status), submitted_by=m.submitted_by, reviewed_by=m.reviewed_by,
        reviewed_at=_as_utc(m.reviewed_at), rejection_reason=m.rejection_reason, reuse_count=m.reuse_count,
        external_listing_enabled=m.external_listing_enabled, created_at=_as_utc(m.created_at), updated_at=_as_utc(m.updated_at),
    )


def _event_to_domain(m: models.UsageEvent) -> UsageEventRecord:
    return UsageEventRecord(
        id=str(m.id), listing_id=str(m.listing_id), consumer_tenant_id=m.consumer_tenant_id, used_at=_as_utc(m.used_at),
    )


class SQLAlchemyAgentMarketplaceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_listing(self, record: ListingRecord) -> ListingRecord:
        m = models.AgentMarketplaceListing(
            id=record.id, tenant_id=record.tenant_id, agent_card_id=record.agent_card_id, name=record.name,
            description=record.description, skills_snapshot=record.skills_snapshot,
            trust_score_snapshot=record.trust_score_snapshot, status=record.status.value,
            submitted_by=record.submitted_by, external_listing_enabled=record.external_listing_enabled,
            reuse_count=record.reuse_count,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _to_domain(m)

    async def get_listing(self, listing_id: str) -> ListingRecord | None:
        m = await self.session.get(models.AgentMarketplaceListing, listing_id)
        return _to_domain(m) if m else None

    async def update_listing(self, record: ListingRecord) -> ListingRecord:
        m = await self.session.get(models.AgentMarketplaceListing, record.id)
        m.name = record.name
        m.description = record.description
        m.skills_snapshot = record.skills_snapshot
        m.trust_score_snapshot = record.trust_score_snapshot
        m.status = record.status.value
        m.reviewed_by = record.reviewed_by
        m.reviewed_at = record.reviewed_at
        m.rejection_reason = record.rejection_reason
        m.reuse_count = record.reuse_count
        m.external_listing_enabled = record.external_listing_enabled
        await self.session.commit()
        await self.session.refresh(m)
        return _to_domain(m)

    async def list_listings(
        self, *, tenant_id: str | None = None, status: ListingStatus | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[ListingRecord], int]:
        filters = []
        if tenant_id is not None:
            filters.append(models.AgentMarketplaceListing.tenant_id == tenant_id)
        if status is not None:
            filters.append(models.AgentMarketplaceListing.status == status.value)

        count_stmt = select(func.count(models.AgentMarketplaceListing.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(models.AgentMarketplaceListing)
            .where(*filters)
            .order_by(
                models.AgentMarketplaceListing.reuse_count.desc(),
                models.AgentMarketplaceListing.trust_score_snapshot.desc().nulls_last(),
                models.AgentMarketplaceListing.created_at,
            )
            .limit(limit)
            .offset(offset)
        )
        rows = await self.session.execute(stmt)
        return [_to_domain(m) for m in rows.scalars().all()], total

    async def create_usage_event(self, record: UsageEventRecord) -> UsageEventRecord:
        m = models.UsageEvent(id=record.id, listing_id=record.listing_id, consumer_tenant_id=record.consumer_tenant_id)
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _event_to_domain(m)

    async def count_usage_events(self, listing_id: str) -> tuple[int, int]:
        total_stmt = select(func.count(models.UsageEvent.id)).where(models.UsageEvent.listing_id == listing_id)
        distinct_stmt = select(func.count(func.distinct(models.UsageEvent.consumer_tenant_id))).where(
            models.UsageEvent.listing_id == listing_id
        )
        total = (await self.session.execute(total_stmt)).scalar_one()
        distinct = (await self.session.execute(distinct_stmt)).scalar_one()
        return total, distinct
