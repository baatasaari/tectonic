"""SQLAlchemy-backed implementation of ContextRepository (LLD §3.1)."""
from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_engineering.core.domain import (
    AssembledItem,
    ContextAssemblyRecord,
    ItemDisposition,
    OntologyConfigRecord,
    PrioritisationWeightsRecord,
)
from context_engineering.db import models


def _ontology_to_domain(m: models.OntologyConfig) -> OntologyConfigRecord:
    return OntologyConfigRecord(
        id=str(m.id), tenant_id=m.tenant_id, version=m.version,
        roles=list(m.roles or []), entity_types=list(m.entity_types or []), policy_tags=list(m.policy_tags or []),
    )


def _weights_to_domain(m: models.PrioritisationWeights) -> PrioritisationWeightsRecord:
    return PrioritisationWeightsRecord(
        id=str(m.id), tenant_id=m.tenant_id, task_type=m.task_type,
        feature_weights=dict(m.feature_weights or {}), last_updated_at=m.last_updated_at,
    )


def _items_from_dicts(items: list[dict], disposition: ItemDisposition) -> list[AssembledItem]:
    return [AssembledItem(source=i["source"], content=i["content"], tokens=i["tokens"], disposition=disposition) for i in items]


class SQLAlchemyContextRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_ontology(self, record: OntologyConfigRecord) -> OntologyConfigRecord:
        m = models.OntologyConfig(
            id=record.id, tenant_id=record.tenant_id, version=record.version,
            roles=record.roles, entity_types=record.entity_types, policy_tags=record.policy_tags,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _ontology_to_domain(m)

    async def get_active_ontology(self, tenant_id: str) -> OntologyConfigRecord | None:
        rows = await self.session.execute(
            select(models.OntologyConfig)
            .where(models.OntologyConfig.tenant_id == tenant_id)
            .order_by(models.OntologyConfig.version.desc())
            .limit(1)
        )
        m = rows.scalars().first()
        return _ontology_to_domain(m) if m else None

    async def get_weights(self, tenant_id: str, task_type: str) -> PrioritisationWeightsRecord | None:
        rows = await self.session.execute(
            select(models.PrioritisationWeights).where(
                models.PrioritisationWeights.tenant_id == tenant_id, models.PrioritisationWeights.task_type == task_type
            )
        )
        m = rows.scalars().first()
        return _weights_to_domain(m) if m else None

    async def upsert_weights(self, record: PrioritisationWeightsRecord) -> PrioritisationWeightsRecord:
        rows = await self.session.execute(
            select(models.PrioritisationWeights).where(
                models.PrioritisationWeights.tenant_id == record.tenant_id,
                models.PrioritisationWeights.task_type == record.task_type,
            )
        )
        m = rows.scalars().first()
        if m is None:
            m = models.PrioritisationWeights(
                id=record.id, tenant_id=record.tenant_id, task_type=record.task_type,
                feature_weights=record.feature_weights,
            )
            self.session.add(m)
        else:
            m.feature_weights = record.feature_weights
        await self.session.commit()
        await self.session.refresh(m)
        return _weights_to_domain(m)

    async def create_assembly_log(self, record: ContextAssemblyRecord) -> ContextAssemblyRecord:
        m = models.ContextAssembly(
            id=record.id, request_ref=record.request_ref, task_type=record.task_type,
            items_included=[asdict(i) for i in record.items_included],
            items_dropped=[asdict(i) for i in record.items_dropped],
            items_summarised=[asdict(i) for i in record.items_summarised],
            total_tokens_used=record.total_tokens_used,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return ContextAssemblyRecord(
            id=str(m.id), request_ref=m.request_ref, task_type=m.task_type,
            items_included=_items_from_dicts(m.items_included, ItemDisposition.INCLUDED),
            items_dropped=_items_from_dicts(m.items_dropped, ItemDisposition.DROPPED),
            items_summarised=_items_from_dicts(m.items_summarised, ItemDisposition.SUMMARISED),
            total_tokens_used=m.total_tokens_used, created_at=m.created_at,
        )
