"""Abstract ports the sync orchestrator depends on: persistence, the
source connector runtime, and the Secrets and Credential Management
dependency."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from data_source_plugins.core.domain import (
    ConnectorConfigRecord,
    DriftIncidentRecord,
    QualityScoreRecord,
    SchemaSnapshotRecord,
    SyncRunRecord,
)


@dataclass
class ExtractionResult:
    records: list[dict[str, Any]] = field(default_factory=list)
    schema: dict[str, Any] = field(default_factory=dict)


class ConnectorRepository(Protocol):
    async def create_connector(self, record: ConnectorConfigRecord) -> ConnectorConfigRecord: ...

    async def get_connector(self, connector_id: str) -> ConnectorConfigRecord | None: ...

    async def update_connector_status(self, connector_id: str, status: str) -> ConnectorConfigRecord: ...

    async def create_schema_snapshot(self, record: SchemaSnapshotRecord) -> SchemaSnapshotRecord: ...

    async def get_latest_schema_snapshot(self, connector_id: str) -> SchemaSnapshotRecord | None: ...

    async def create_sync_run(self, record: SyncRunRecord) -> SyncRunRecord: ...

    async def update_sync_run(self, record: SyncRunRecord) -> SyncRunRecord: ...

    async def list_sync_runs(self, connector_id: str) -> list[SyncRunRecord]: ...

    async def create_quality_score(self, record: QualityScoreRecord) -> QualityScoreRecord: ...

    async def get_latest_quality_score(self, connector_id: str) -> QualityScoreRecord | None: ...

    async def create_drift_incident(self, record: DriftIncidentRecord) -> DriftIncidentRecord: ...

    async def list_drift_incidents(self, connector_id: str) -> list[DriftIncidentRecord]: ...


class SourceConnectorRuntime(Protocol):
    async def extract(
        self, *, source_type: str, connection_config: dict[str, Any], credentials: dict[str, Any],
        query: dict[str, Any] | None = None,
    ) -> ExtractionResult:
        """Runs the actual extraction against the source system, returning
        raw records plus the schema observed for this extraction."""
        ...


class SecretsClient(Protocol):
    async def resolve(self, secrets_ref: str) -> dict[str, Any]:
        """Resolves a secrets_ref pointer to actual credential material.
        No credentials are ever stored by this module itself."""
        ...
