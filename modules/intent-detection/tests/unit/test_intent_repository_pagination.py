"""Pagination behavior for InMemoryIntentRepository.list_drift_reports."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from intent_detection.core.domain import DriftReportRecord, new_id
from intent_detection.core.fakes import InMemoryIntentRepository

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _report(tenant_id: str, drift_score: float, created_at: datetime) -> DriftReportRecord:
    return DriftReportRecord(
        id=new_id(), tenant_id=tenant_id, taxonomy_version=1,
        drift_score=drift_score, flagged_intents=[], created_at=created_at,
    )


@pytest.mark.asyncio
async def test_list_drift_reports_paginates_across_pages():
    repo = InMemoryIntentRepository()
    reports = []
    for i, score in enumerate((0.1, 0.2, 0.3)):
        r = await repo.create_drift_report(_report("tenant-a", score, _BASE_TIME + timedelta(minutes=i)))
        reports.append(r)

    # newest first: reports[2], reports[1], reports[0]
    page1, total1 = await repo.list_drift_reports("tenant-a", limit=2, offset=0)
    assert total1 == 3
    assert [r.id for r in page1] == [reports[2].id, reports[1].id]

    page2, total2 = await repo.list_drift_reports("tenant-a", limit=2, offset=2)
    assert total2 == 3
    assert [r.id for r in page2] == [reports[0].id]


@pytest.mark.asyncio
async def test_list_drift_reports_empty_result_set():
    repo = InMemoryIntentRepository()
    items, total = await repo.list_drift_reports("tenant-with-no-reports")
    assert items == []
    assert total == 0


@pytest.mark.asyncio
async def test_list_drift_reports_ordered_newest_first():
    repo = InMemoryIntentRepository()
    first = await repo.create_drift_report(_report("tenant-a", 0.1, _BASE_TIME))
    second = await repo.create_drift_report(_report("tenant-a", 0.2, _BASE_TIME + timedelta(minutes=1)))

    items, total = await repo.list_drift_reports("tenant-a", limit=50, offset=0)
    assert total == 2
    assert [r.id for r in items] == [second.id, first.id]
