"""Sync Service — the orchestrator tying together extraction, drift
detection, normalisation and quality scoring (LLD §Level 3 "Sequence:
scheduled sync with schema drift detected and auto-adapted", and the
sync run lifecycle state diagram).
"""
from __future__ import annotations

from datetime import UTC, datetime

from data_source_plugins.config import DriftConfig, QualityConfig
from data_source_plugins.core import normalizer, quality_scorer, schema_drift
from data_source_plugins.core.domain import (
    ConnectorNotFoundError,
    DriftIncidentRecord,
    QualityScoreRecord,
    SchemaSnapshotRecord,
    SyncOutcome,
    SyncRunRecord,
    SyncRunStatus,
    new_id,
)
from data_source_plugins.core.ports import (
    ConnectorRepository,
    SecretsClient,
    SourceConnectorRuntime,
)


class SyncService:
    def __init__(
        self,
        repository: ConnectorRepository,
        connector_runtime: SourceConnectorRuntime,
        secrets_client: SecretsClient,
        drift_config: DriftConfig,
        quality_config: QualityConfig,
    ) -> None:
        self._repository = repository
        self._runtime = connector_runtime
        self._secrets = secrets_client
        self._drift_config = drift_config
        self._quality_config = quality_config

    async def sync(self, connector_id: str, *, query: dict | None = None) -> SyncOutcome:
        connector = await self._repository.get_connector(connector_id)
        if connector is None:
            raise ConnectorNotFoundError(connector_id)

        sync_run = SyncRunRecord(id=new_id(), connector_id=connector_id, status=SyncRunStatus.RUNNING)
        sync_run = await self._repository.create_sync_run(sync_run)

        try:
            credentials = await self._secrets.resolve(connector.secrets_ref)
            extraction = await self._runtime.extract(
                source_type=connector.source_type, connection_config=connector.connection_config,
                credentials=credentials, query=query,
            )
        except Exception:
            sync_run.status = SyncRunStatus.FAILED
            sync_run.completed_at = datetime.now(UTC)
            await self._repository.update_sync_run(sync_run)
            raise

        current_schema = extraction.schema or normalizer.infer_schema(extraction.records)
        previous_snapshot = await self._repository.get_latest_schema_snapshot(connector_id)

        drift_incident: DriftIncidentRecord | None = None
        mapping = current_schema

        if previous_snapshot is not None:
            detection = schema_drift.detect_drift(previous_snapshot.schema, current_schema)
            if detection.drift_detected:
                auto_adapted = schema_drift.should_auto_adapt(
                    detection.classification,
                    auto_adapt_enabled=self._drift_config.auto_adapt_enabled,
                    auto_adapt_scope=self._drift_config.auto_adapt_scope,
                )
                drift_incident = DriftIncidentRecord(
                    id=new_id(), connector_id=connector_id, schema_diff=detection.schema_diff,
                    classification=detection.classification, auto_adapted=auto_adapted,
                )
                drift_incident = await self._repository.create_drift_incident(drift_incident)

                if auto_adapted:
                    mapping = current_schema
                    await self._repository.create_schema_snapshot(
                        SchemaSnapshotRecord(
                            id=new_id(), connector_id=connector_id, schema=current_schema,
                            version=previous_snapshot.version + 1,
                        )
                    )
                else:
                    # Not adapted: keep normalising against the last-known
                    # mapping and require manual review before proceeding.
                    mapping = previous_snapshot.schema
                    sync_run.status = SyncRunStatus.MANUAL_REVIEW_REQUIRED
                    sync_run.records_synced = 0
                    sync_run.completed_at = datetime.now(UTC)
                    await self._repository.update_sync_run(sync_run)
                    await self._repository.update_connector_status(connector_id, "paused")
                    return SyncOutcome(
                        sync_run=sync_run, drift_incident=drift_incident, quality_score=None,
                        normalised_record_count=0,
                    )
        else:
            await self._repository.create_schema_snapshot(
                SchemaSnapshotRecord(id=new_id(), connector_id=connector_id, schema=current_schema, version=1)
            )

        normalised = normalizer.normalise(extraction.records, mapping)
        breakdown = quality_scorer.score(extraction.records, mapping, self._quality_config)
        quality_score = await self._repository.create_quality_score(
            QualityScoreRecord(
                id=new_id(), connector_id=connector_id, sync_run_id=sync_run.id,
                completeness_score=breakdown.completeness_score, freshness_score=breakdown.freshness_score,
                format_validity_score=breakdown.format_validity_score, overall_score=breakdown.overall_score,
            )
        )

        sync_run.status = SyncRunStatus.COMPLETED
        sync_run.records_synced = len(normalised)
        sync_run.completed_at = datetime.now(UTC)
        await self._repository.update_sync_run(sync_run)

        return SyncOutcome(
            sync_run=sync_run, drift_incident=drift_incident, quality_score=quality_score,
            normalised_record_count=len(normalised),
        )

    async def query(self, connector_id: str, query: dict) -> list[dict]:
        """Point query, synchronous — extracts without persisting a
        SyncRun/QualityScore/DriftIncident trail (LLD API surface: `POST
        /connectors/{id}/query`)."""
        connector = await self._repository.get_connector(connector_id)
        if connector is None:
            raise ConnectorNotFoundError(connector_id)
        credentials = await self._secrets.resolve(connector.secrets_ref)
        extraction = await self._runtime.extract(
            source_type=connector.source_type, connection_config=connector.connection_config,
            credentials=credentials, query=query,
        )
        schema = extraction.schema or normalizer.infer_schema(extraction.records)
        return normalizer.normalise(extraction.records, schema)
