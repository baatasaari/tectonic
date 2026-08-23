"""SQLAlchemy-backed implementation of RAGRepository (LLD §3.1)."""
from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_rag.core.domain import (
    Provenance,
    RetrievalHopRecord,
    RetrievalOutcome,
    RetrievalRequestRecord,
    RetrievalResultRecord,
    RetrievalSource,
    RetrievedItem,
)
from agentic_rag.db import models


def _item_to_dict(item: RetrievedItem) -> dict:
    return {"content": item.content, "source": item.source.value, "provenance": asdict(item.provenance), "retrieval_score": item.retrieval_score}


def _item_from_dict(d: dict) -> RetrievedItem:
    return RetrievedItem(
        content=d["content"], source=RetrievalSource(d["source"]),
        provenance=Provenance(**d["provenance"]), retrieval_score=d.get("retrieval_score", 0.0),
    )


def _request_to_domain(m: models.RetrievalRequest) -> RetrievalRequestRecord:
    return RetrievalRequestRecord(
        id=str(m.id), tenant_id=m.tenant_id, query=m.query, scope=list(m.scope or []),
        max_hops=m.max_hops, groundedness_threshold=m.groundedness_threshold, created_at=m.created_at,
    )


def _hop_to_domain(m: models.RetrievalHop) -> RetrievalHopRecord:
    return RetrievalHopRecord(
        id=str(m.id), request_id=str(m.request_id), hop_number=m.hop_number,
        retrieved_items=[_item_from_dict(i) for i in (m.retrieved_items or [])],
        groundedness_score=m.groundedness_score, reformulated_query=m.reformulated_query, created_at=m.created_at,
    )


def _result_to_domain(m: models.RetrievalResult) -> RetrievalResultRecord:
    return RetrievalResultRecord(
        request_id=str(m.request_id), final_context=m.final_context, total_hops=m.total_hops,
        final_groundedness_score=m.final_groundedness_score,
        provenance_chain=[Provenance(**p) for p in (m.provenance_chain or [])],
        outcome=RetrievalOutcome(m.outcome),
    )


class SQLAlchemyRAGRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_request(self, record: RetrievalRequestRecord) -> RetrievalRequestRecord:
        m = models.RetrievalRequest(
            id=record.id, tenant_id=record.tenant_id, query=record.query, scope=record.scope,
            max_hops=record.max_hops, groundedness_threshold=record.groundedness_threshold,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _request_to_domain(m)

    async def get_request(self, request_id: str) -> RetrievalRequestRecord | None:
        m = await self.session.get(models.RetrievalRequest, request_id)
        return _request_to_domain(m) if m else None

    async def create_hop(self, record: RetrievalHopRecord) -> RetrievalHopRecord:
        m = models.RetrievalHop(
            id=record.id, request_id=record.request_id, hop_number=record.hop_number,
            reformulated_query=record.reformulated_query,
            retrieved_items=[_item_to_dict(i) for i in record.retrieved_items],
            groundedness_score=record.groundedness_score,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _hop_to_domain(m)

    async def list_hops(self, request_id: str) -> list[RetrievalHopRecord]:
        rows = await self.session.execute(
            select(models.RetrievalHop)
            .where(models.RetrievalHop.request_id == request_id)
            .order_by(models.RetrievalHop.hop_number)
        )
        return [_hop_to_domain(m) for m in rows.scalars().all()]

    async def create_result(self, record: RetrievalResultRecord) -> RetrievalResultRecord:
        m = models.RetrievalResult(
            request_id=record.request_id, final_context=record.final_context, total_hops=record.total_hops,
            final_groundedness_score=record.final_groundedness_score,
            provenance_chain=[asdict(p) for p in record.provenance_chain], outcome=record.outcome.value,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _result_to_domain(m)

    async def get_result(self, request_id: str) -> RetrievalResultRecord | None:
        m = await self.session.get(models.RetrievalResult, request_id)
        return _result_to_domain(m) if m else None
