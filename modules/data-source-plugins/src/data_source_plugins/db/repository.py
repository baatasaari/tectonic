"""SQLAlchemy-backed implementation of ConnectorRepository (LLD §3)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_source_plugins.core.domain import (
    ConnectorConfigRecord,
    ConnectorStatus,
    DriftClassification,
    DriftIncidentRecord,
    QualityScoreRecord,
    SchemaSnapshotRecord,
    SyncRunRecord,
    SyncRunStatus,
)
from data_source_plugins.db import models


def _connector_to_domain(m: models.ConnectorConfig) -> ConnectorConfigRecord:
    return ConnectorConfigRecord(
        id=str(m.id), tenant_id=m.tenant_id, source_type=m.source_type,
        connection_config=dict(m.connection_config or {}), secrets_ref=m.secrets_ref,
        sync_schedule=m.sync_schedule, status=ConnectorStatus(m.status), created_at=m.created_at,
    )


def _snapshot_to_domain(m: models.SchemaSnapshot) -> SchemaSnapshotRecord:
    return SchemaSnapshotRecord(
        id=str(m.id), connector_id=str(m.connector_id), schema=dict(m.schema_json or {}),
        version=m.version, captured_at=m.captured_at,
    )


def _sync_run_to_domain(m: models.SyncRun) -> SyncRunRecord:
    return SyncRunRecord(
        id=str(m.id), connector_id=str(m.connector_id), status=SyncRunStatus(m.status),
        records_synced=m.records_synced, started_at=m.started_at, completed_at=m.completed_at,
    )


def _quality_score_to_domain(m: models.QualityScore) -> QualityScoreRecord:
    return QualityScoreRecord(
        id=str(m.id), connector_id=str(m.connector_id), sync_run_id=str(m.sync_run_id),
        completeness_score=m.completeness_score, freshness_score=m.freshness_score,
        format_validity_score=m.format_validity_score, overall_score=m.overall_score, computed_at=m.computed_at,
    )


def _drift_incident_to_domain(m: models.DriftIncident) -> DriftIncidentRecord:
    return DriftIncidentRecord(
        id=str(m.id), connector_id=str(m.connector_id), schema_diff=dict(m.schema_diff or {}),
        classification=DriftClassification(m.classification), auto_adapted=m.auto_adapted,
        resolved_by=m.resolved_by, created_at=m.created_at,
    )


class SQLAlchemyConnectorRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_connector(self, record: ConnectorConfigRecord) -> ConnectorConfigRecord:
        m = models.ConnectorConfig(
            id=record.id, tenant_id=record.tenant_id, source_type=record.source_type,
            connection_config=record.connection_config, secrets_ref=record.secrets_ref,
            sync_schedule=record.sync_schedule, status=record.status.value,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _connector_to_domain(m)

    async def get_connector(self, connector_id: str) -> ConnectorConfigRecord | None:
        m = await self.session.get(models.ConnectorConfig, connector_id)
        return _connector_to_domain(m) if m else None

    async def update_connector_status(self, connector_id: str, status: str) -> ConnectorConfigRecord:
        m = await self.session.get(models.ConnectorConfig, connector_id)
        if m is None:
            raise LookupError(connector_id)
        m.status = status
        await self.session.commit()
        await self.session.refresh(m)
        return _connector_to_domain(m)

    async def create_schema_snapshot(self, record: SchemaSnapshotRecord) -> SchemaSnapshotRecord:
        m = models.SchemaSnapshot(
            id=record.id, connector_id=record.connector_id, schema_json=record.schema, version=record.version,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _snapshot_to_domain(m)

    async def get_latest_schema_snapshot(self, connector_id: str) -> SchemaSnapshotRecord | None:
        rows = await self.session.execute(
            select(models.SchemaSnapshot)
            .where(models.SchemaSnapshot.connector_id == connector_id)
            .order_by(models.SchemaSnapshot.version.desc())
            .limit(1)
        )
        m = rows.scalars().first()
        return _snapshot_to_domain(m) if m else None

    async def create_sync_run(self, record: SyncRunRecord) -> SyncRunRecord:
        m = models.SyncRun(
            id=record.id, connector_id=record.connector_id, status=record.status.value,
            records_synced=record.records_synced, completed_at=record.completed_at,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _sync_run_to_domain(m)

    async def update_sync_run(self, record: SyncRunRecord) -> SyncRunRecord:
        m = await self.session.get(models.SyncRun, record.id)
        if m is None:
            raise LookupError(record.id)
        m.status = record.status.value
        m.records_synced = record.records_synced
        m.completed_at = record.completed_at
        await self.session.commit()
        await self.session.refresh(m)
        return _sync_run_to_domain(m)

    async def list_sync_runs(self, connector_id: str) -> list[SyncRunRecord]:
        rows = await self.session.execute(
            select(models.SyncRun).where(models.SyncRun.connector_id == connector_id)
        )
        return [_sync_run_to_domain(m) for m in rows.scalars().all()]

    async def create_quality_score(self, record: QualityScoreRecord) -> QualityScoreRecord:
        m = models.QualityScore(
            id=record.id, connector_id=record.connector_id, sync_run_id=record.sync_run_id,
            completeness_score=record.completeness_score, freshness_score=record.freshness_score,
            format_validity_score=record.format_validity_score, overall_score=record.overall_score,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _quality_score_to_domain(m)

    async def get_latest_quality_score(self, connector_id: str) -> QualityScoreRecord | None:
        rows = await self.session.execute(
            select(models.QualityScore)
            .where(models.QualityScore.connector_id == connector_id)
            .order_by(models.QualityScore.computed_at.desc())
            .limit(1)
        )
        m = rows.scalars().first()
        return _quality_score_to_domain(m) if m else None

    async def create_drift_incident(self, record: DriftIncidentRecord) -> DriftIncidentRecord:
        m = models.DriftIncident(
            id=record.id, connector_id=record.connector_id, schema_diff=record.schema_diff,
            classification=record.classification.value, auto_adapted=record.auto_adapted,
            resolved_by=record.resolved_by,
        )
        self.session.add(m)
        await self.session.commit()
        await self.session.refresh(m)
        return _drift_incident_to_domain(m)

    async def list_drift_incidents(self, connector_id: str) -> list[DriftIncidentRecord]:
        rows = await self.session.execute(
            select(models.DriftIncident).where(models.DriftIncident.connector_id == connector_id)
        )
        return [_drift_incident_to_domain(m) for m in rows.scalars().all()]
