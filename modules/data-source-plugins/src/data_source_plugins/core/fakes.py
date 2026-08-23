"""In-memory fakes for the ports in core/ports.py — the unit-test tier,
mirroring the other modules' core/fakes.py.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

from data_source_plugins.core.domain import (
    ConnectorConfigRecord,
    DriftIncidentRecord,
    QualityScoreRecord,
    SchemaSnapshotRecord,
    SyncRunRecord,
)
from data_source_plugins.core.ports import ExtractionResult


class InMemoryConnectorRepository:
    def __init__(self) -> None:
        self.connectors: dict[str, ConnectorConfigRecord] = {}
        self.schema_snapshots: dict[str, list[SchemaSnapshotRecord]] = {}
        self.sync_runs: dict[str, SyncRunRecord] = {}
        self.quality_scores: dict[str, list[QualityScoreRecord]] = {}
        self.drift_incidents: dict[str, list[DriftIncidentRecord]] = {}

    async def create_connector(self, record: ConnectorConfigRecord) -> ConnectorConfigRecord:
        self.connectors[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_connector(self, connector_id: str) -> ConnectorConfigRecord | None:
        rec = self.connectors.get(connector_id)
        return copy.deepcopy(rec) if rec else None

    async def update_connector_status(self, connector_id: str, status: str) -> ConnectorConfigRecord:
        rec = self.connectors[connector_id]
        rec = replace(rec, status=type(rec.status)(status))
        self.connectors[connector_id] = rec
        return copy.deepcopy(rec)

    async def create_schema_snapshot(self, record: SchemaSnapshotRecord) -> SchemaSnapshotRecord:
        self.schema_snapshots.setdefault(record.connector_id, []).append(copy.deepcopy(record))
        return copy.deepcopy(record)

    async def get_latest_schema_snapshot(self, connector_id: str) -> SchemaSnapshotRecord | None:
        snapshots = self.schema_snapshots.get(connector_id) or []
        if not snapshots:
            return None
        return copy.deepcopy(max(snapshots, key=lambda s: s.version))

    async def create_sync_run(self, record: SyncRunRecord) -> SyncRunRecord:
        self.sync_runs[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def update_sync_run(self, record: SyncRunRecord) -> SyncRunRecord:
        self.sync_runs[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def list_sync_runs(self, connector_id: str) -> list[SyncRunRecord]:
        return [copy.deepcopy(r) for r in self.sync_runs.values() if r.connector_id == connector_id]

    async def create_quality_score(self, record: QualityScoreRecord) -> QualityScoreRecord:
        self.quality_scores.setdefault(record.connector_id, []).append(copy.deepcopy(record))
        return copy.deepcopy(record)

    async def get_latest_quality_score(self, connector_id: str) -> QualityScoreRecord | None:
        scores = self.quality_scores.get(connector_id) or []
        if not scores:
            return None
        return copy.deepcopy(max(scores, key=lambda s: s.computed_at))

    async def create_drift_incident(self, record: DriftIncidentRecord) -> DriftIncidentRecord:
        self.drift_incidents.setdefault(record.connector_id, []).append(copy.deepcopy(record))
        return copy.deepcopy(record)

    async def list_drift_incidents(self, connector_id: str) -> list[DriftIncidentRecord]:
        return [copy.deepcopy(r) for r in self.drift_incidents.get(connector_id, [])]


class StubSourceConnectorRuntime:
    """Deviation from the LLD's Airbyte/PyAirbyte runtime — see the
    module README's "Design notes vs. the LLD"."""

    def __init__(self) -> None:
        self.canned_result: ExtractionResult | None = None
        self.calls: list[dict[str, Any]] = []
        self.results_by_source_type: dict[str, ExtractionResult] = {}

    async def extract(
        self, *, source_type: str, connection_config: dict[str, Any], credentials: dict[str, Any],
        query: dict[str, Any] | None = None,
    ) -> ExtractionResult:
        self.calls.append({
            "source_type": source_type, "connection_config": connection_config,
            "credentials": credentials, "query": query,
        })
        if source_type in self.results_by_source_type:
            return self.results_by_source_type[source_type]
        if self.canned_result is not None:
            return self.canned_result
        return ExtractionResult(
            records=[{"id": 1, "name": "sample"}, {"id": 2, "name": "sample-2"}],
            schema={"id": "integer", "name": "string"},
        )


class StubSecretsClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def resolve(self, secrets_ref: str) -> dict[str, Any]:
        self.calls.append(secrets_ref)
        return {"api_key": "fake-key-for-" + secrets_ref} if secrets_ref else {}
