"""In-memory fakes for the ports in core/ports.py — the unit-test tier,
mirroring the other modules' core/fakes.py.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

from intent_detection.core.domain import (
    ClassificationLogRecord,
    DriftReportRecord,
    IntentTaxonomyRecord,
    TaxonomyStatus,
)


class InMemoryIntentRepository:
    def __init__(self) -> None:
        self.taxonomies: dict[str, IntentTaxonomyRecord] = {}
        self.logs: list[ClassificationLogRecord] = []
        self.drift_reports: list[DriftReportRecord] = []

    async def create_taxonomy(self, record: IntentTaxonomyRecord) -> IntentTaxonomyRecord:
        self.taxonomies[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_taxonomy(self, taxonomy_id: str) -> IntentTaxonomyRecord | None:
        rec = self.taxonomies.get(taxonomy_id)
        return copy.deepcopy(rec) if rec else None

    async def get_active_taxonomy(self, tenant_id: str) -> IntentTaxonomyRecord | None:
        candidates = [
            t for t in self.taxonomies.values() if t.tenant_id == tenant_id and t.status == TaxonomyStatus.ACTIVE
        ]
        if not candidates:
            return None
        return copy.deepcopy(max(candidates, key=lambda t: t.version))

    async def get_taxonomy_by_version(self, tenant_id: str, version: int) -> IntentTaxonomyRecord | None:
        for t in self.taxonomies.values():
            if t.tenant_id == tenant_id and t.version == version:
                return copy.deepcopy(t)
        return None

    async def activate_taxonomy(self, taxonomy_id: str) -> IntentTaxonomyRecord:
        rec = self.taxonomies[taxonomy_id]
        rec = replace(rec, status=TaxonomyStatus.ACTIVE)
        self.taxonomies[taxonomy_id] = rec
        return copy.deepcopy(rec)

    async def create_classification_log(self, record: ClassificationLogRecord) -> ClassificationLogRecord:
        self.logs.append(copy.deepcopy(record))
        return copy.deepcopy(record)

    async def list_classification_logs(
        self, tenant_id: str, taxonomy_version: int | None = None
    ) -> list[ClassificationLogRecord]:
        return [
            copy.deepcopy(log)
            for log in self.logs
            if log.tenant_id == tenant_id and (taxonomy_version is None or log.taxonomy_version == taxonomy_version)
        ]

    async def create_drift_report(self, record: DriftReportRecord) -> DriftReportRecord:
        self.drift_reports.append(copy.deepcopy(record))
        return copy.deepcopy(record)

    async def list_drift_reports(self, tenant_id: str) -> list[DriftReportRecord]:
        return [copy.deepcopy(r) for r in self.drift_reports if r.tenant_id == tenant_id]


class StubLLMGatewayClient:
    def __init__(self) -> None:
        self.canned_response: list[dict[str, Any]] | None = None
        self.calls: list[dict[str, Any]] = []

    async def classify_structured(
        self, *, text: str, taxonomy: list[dict[str, Any]], tenant_id: str
    ) -> list[dict[str, Any]]:
        self.calls.append({"text": text, "taxonomy": taxonomy, "tenant_id": tenant_id})
        if self.canned_response is not None:
            return self.canned_response
        # Default stub: "detect" the first two taxonomy intents with
        # descending confidence, a stand-in for genuine multi-intent output.
        return [{"name": t["name"], "confidence": 0.9 - 0.1 * i} for i, t in enumerate(taxonomy[:2])]
