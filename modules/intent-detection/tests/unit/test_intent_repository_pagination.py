"""Pagination behavior for InMemoryIntentRepository.list_drift_reports."""
from __future__ import annotations

import pytest

from intent_detection.core.domain import DriftReportRecord, new_id
from intent_detection.core.fakes import InMemoryIntentRepository


def _report(tenant_id: str, drift_score: float) -> DriftReportRecord:
    return DriftReportRecord(
        id=new_id(), tenant_id=tenant_id, taxonomy_version=1,
        drift_score=drift_score, flagged_intents=[],
    )


@pytest.mark.asyncio
async def test_list_drift_reports_paginates_across_pages():
    repo = InMemoryIntentRepository()
    reports = []
    for score in (0.1, 0.2, 0.3):
        r = await repo.create_drift_report(_report("tenant-a", score))
        reports.append(r)

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
    first = await repo.create_drift_report(_report("tenant-a", 0.1))
    second = await repo.create_drift_report(_report("tenant-a", 0.2))

    items, total = await repo.list_drift_reports("tenant-a", limit=50, offset=0)
    assert total == 2
    assert [r.id for r in items] == [second.id, first.id]
