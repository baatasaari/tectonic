"""Abstract ports the classification engine depends on: taxonomy/log
persistence and the LLM Gateway fallback dependency."""
from __future__ import annotations

from typing import Any, Protocol

from intent_detection.core.domain import (
    ClassificationLogRecord,
    DriftReportRecord,
    IntentTaxonomyRecord,
)


class IntentRepository(Protocol):
    async def create_taxonomy(self, record: IntentTaxonomyRecord) -> IntentTaxonomyRecord: ...

    async def get_taxonomy(self, taxonomy_id: str) -> IntentTaxonomyRecord | None: ...

    async def get_active_taxonomy(self, tenant_id: str) -> IntentTaxonomyRecord | None: ...

    async def get_taxonomy_by_version(self, tenant_id: str, version: int) -> IntentTaxonomyRecord | None: ...

    async def activate_taxonomy(self, taxonomy_id: str) -> IntentTaxonomyRecord: ...

    async def create_classification_log(self, record: ClassificationLogRecord) -> ClassificationLogRecord: ...

    async def list_classification_logs(
        self, tenant_id: str, taxonomy_version: int | None = None
    ) -> list[ClassificationLogRecord]: ...

    async def create_drift_report(self, record: DriftReportRecord) -> DriftReportRecord: ...

    async def list_drift_reports(self, tenant_id: str) -> list[DriftReportRecord]: ...


class LLMGatewayClient(Protocol):
    async def classify_structured(
        self, *, text: str, taxonomy: list[dict[str, Any]], tenant_id: str
    ) -> list[dict[str, Any]]:
        """Returns a list of {"name": str, "confidence": float} — the
        structured multi-intent fallback classification."""
        ...
