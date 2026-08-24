"""Tests for core/ingestion_service.py."""
from __future__ import annotations


async def test_ingest_assigns_sequence_number_1_to_a_tenants_first_event(harness):
    event = await harness.ingestion_service.ingest(
        tenant_id="t1", source_module="workflow-engine", payload={"event_type": "handoff"},
    )

    assert event.sequence_number == 1
    assert event.prev_hash is None
    assert event.entry_hash


async def test_ingest_chains_sequential_events_for_the_same_tenant(harness):
    first = await harness.ingestion_service.ingest(
        tenant_id="t1", source_module="workflow-engine", payload={"event_type": "a"},
    )
    second = await harness.ingestion_service.ingest(
        tenant_id="t1", source_module="workflow-engine", payload={"event_type": "b"},
    )

    assert second.sequence_number == 2
    assert second.prev_hash == first.entry_hash


async def test_ingest_keeps_separate_tenants_sequence_numbers_independent(harness):
    await harness.ingestion_service.ingest(tenant_id="t1", source_module="m1", payload={"event_type": "a"})
    other_tenant_event = await harness.ingestion_service.ingest(
        tenant_id="t2", source_module="m1", payload={"event_type": "a"},
    )

    assert other_tenant_event.sequence_number == 1
    assert other_tenant_event.prev_hash is None


async def test_ingest_normalizes_event_type_from_either_known_key(harness):
    via_event_type = await harness.ingestion_service.ingest(
        tenant_id="t1", source_module="m1", payload={"event_type": "handoff"},
    )
    via_event = await harness.ingestion_service.ingest(
        tenant_id="t1", source_module="m1", payload={"event": "oversight_decision"},
    )
    via_neither = await harness.ingestion_service.ingest(tenant_id="t1", source_module="m1", payload={})

    assert via_event_type.event_type == "handoff"
    assert via_event.event_type == "oversight_decision"
    assert via_neither.event_type == "unknown"


async def test_ingest_preserves_the_full_original_payload(harness):
    payload = {"event_type": "handoff", "session_id": "s1", "detail": {"nested": True}}

    event = await harness.ingestion_service.ingest(tenant_id="t1", source_module="m1", payload=payload)

    assert event.payload == payload
