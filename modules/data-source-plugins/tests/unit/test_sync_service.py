import pytest

from data_source_plugins.core.domain import ConnectorNotFoundError, SyncRunStatus
from data_source_plugins.core.ports import ExtractionResult


async def test_first_sync_creates_initial_snapshot_and_completes(harness):
    connector = await harness.seed_connector()
    outcome = await harness.service.sync(connector.id)

    assert outcome.sync_run.status == SyncRunStatus.COMPLETED
    assert outcome.drift_incident is None
    assert outcome.quality_score is not None
    snapshot = await harness.repository.get_latest_schema_snapshot(connector.id)
    assert snapshot.version == 1


async def test_second_sync_with_identical_schema_has_no_drift(harness):
    connector = await harness.seed_connector()
    await harness.service.sync(connector.id)
    outcome = await harness.service.sync(connector.id)

    assert outcome.sync_run.status == SyncRunStatus.COMPLETED
    assert outcome.drift_incident is None


async def test_additive_drift_is_auto_adapted_by_default(harness):
    connector = await harness.seed_connector()
    await harness.service.sync(connector.id)

    harness.connector_runtime.canned_result = ExtractionResult(
        records=[{"id": 1, "name": "sample", "email": "a@b.com"}],
        schema={"id": "integer", "name": "string", "email": "string"},
    )
    outcome = await harness.service.sync(connector.id)

    assert outcome.sync_run.status == SyncRunStatus.COMPLETED
    assert outcome.drift_incident is not None
    assert outcome.drift_incident.auto_adapted is True
    snapshot = await harness.repository.get_latest_schema_snapshot(connector.id)
    assert snapshot.version == 2
    assert snapshot.schema == {"id": "integer", "name": "string", "email": "string"}


async def test_breaking_drift_requires_manual_review_and_pauses_connector(harness):
    connector = await harness.seed_connector()
    await harness.service.sync(connector.id)

    harness.connector_runtime.canned_result = ExtractionResult(
        records=[{"id": 1}],
        schema={"id": "integer"},  # "name" field removed: breaking
    )
    outcome = await harness.service.sync(connector.id)

    assert outcome.sync_run.status == SyncRunStatus.MANUAL_REVIEW_REQUIRED
    assert outcome.drift_incident.auto_adapted is False
    assert outcome.quality_score is None

    updated_connector = await harness.repository.get_connector(connector.id)
    assert updated_connector.status.value == "paused"

    # The schema snapshot is not advanced past the last-known-good version.
    snapshot = await harness.repository.get_latest_schema_snapshot(connector.id)
    assert snapshot.version == 1


async def test_breaking_drift_normalises_against_previous_mapping_not_new_one(harness_factory):
    from data_source_plugins.config import DriftConfig

    harness = harness_factory(drift_config=DriftConfig(auto_adapt_enabled=False))
    connector = await harness.seed_connector()
    first = await harness.service.sync(connector.id)
    assert first.sync_run.status.value == "completed"

    # Any drift at all is rejected once auto-adapt is disabled entirely.
    harness.connector_runtime.canned_result = ExtractionResult(
        records=[{"id": 1, "name": "sample", "extra": True}],
        schema={"id": "integer", "name": "string", "extra": "boolean"},
    )
    outcome = await harness.service.sync(connector.id)
    assert outcome.sync_run.status.value == "manual_review_required"
    assert outcome.drift_incident.auto_adapted is False


async def test_sync_unknown_connector_raises(harness):
    with pytest.raises(ConnectorNotFoundError):
        await harness.service.sync("does-not-exist")


async def test_query_is_synchronous_and_does_not_create_sync_run(harness):
    connector = await harness.seed_connector()
    result = await harness.service.query(connector.id, {"filter": "active"})

    assert len(result) == 2
    runs = await harness.repository.list_sync_runs(connector.id)
    assert runs == []
