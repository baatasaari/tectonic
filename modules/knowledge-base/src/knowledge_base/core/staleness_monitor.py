"""Staleness Monitor (LLD §2 sub-components): scheduled job flagging
documents past their staleness threshold — a document-level override
takes precedence over the tenant's configured default.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from knowledge_base.core.domain import DocumentRecord, DocumentStatus


@dataclass
class StalenessReport:
    stale_document_ids: list[str]
    total_active_or_stale: int

    @property
    def stale_ratio(self) -> float:
        if self.total_active_or_stale == 0:
            return 0.0
        return len(self.stale_document_ids) / self.total_active_or_stale


def is_stale(document: DocumentRecord, default_threshold_days: int, *, reference_time: datetime | None = None) -> bool:
    if document.status == DocumentStatus.ARCHIVED:
        return False
    threshold_days = document.staleness_threshold_days or default_threshold_days
    now = reference_time or datetime.now(UTC)
    age_days = (now - document.last_reviewed_at).total_seconds() / 86400.0
    return age_days > threshold_days


def evaluate(
    documents: list[DocumentRecord], default_threshold_days: int, *, reference_time: datetime | None = None,
) -> StalenessReport:
    candidates = [d for d in documents if d.status != DocumentStatus.ARCHIVED]
    stale_ids = [d.id for d in candidates if is_stale(d, default_threshold_days, reference_time=reference_time)]
    return StalenessReport(stale_document_ids=stale_ids, total_active_or_stale=len(candidates))
