from datetime import UTC, datetime, timedelta


def _span(name, offset=0, **overrides):
    start = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=offset)
    return {
        "span_id": overrides.pop("span_id", name), "name": name, "service_name": overrides.pop("service_name", "workflow-engine"),
        "start_time": start, "end_time": start + timedelta(seconds=overrides.pop("duration", 1)),
        "attributes": overrides.pop("attributes", {}), "status": overrides.pop("status", "ok"),
    }


async def test_ingest_persists_all_spans(harness):
    spans = [_span("retrieve"), _span("classify"), _span("respond")]
    count = await harness.ingestion_service.ingest("t1", "trace-1", spans, "support_flow")

    assert count == 3
    persisted = await harness.repository.list_spans_for_trace("t1", "trace-1")
    assert len(persisted) == 3
    assert {s.name for s in persisted} == {"retrieve", "classify", "respond"}


async def test_ingest_tags_workflow_type_on_every_span(harness):
    await harness.ingestion_service.ingest("t1", "trace-1", [_span("retrieve")], "support_flow")
    persisted = await harness.repository.list_spans_for_trace("t1", "trace-1")
    assert persisted[0].workflow_type == "support_flow"


async def test_ingest_no_workflow_type_is_allowed(harness):
    count = await harness.ingestion_service.ingest("t1", "trace-2", [_span("step")], None)
    assert count == 1
    persisted = await harness.repository.list_spans_for_trace("t1", "trace-2")
    assert persisted[0].workflow_type is None


async def test_ingest_scoped_by_tenant(harness):
    await harness.ingestion_service.ingest("t1", "trace-shared-id", [_span("a")], None)
    await harness.ingestion_service.ingest("t2", "trace-shared-id", [_span("b"), _span("c")], None)

    t1_spans = await harness.repository.list_spans_for_trace("t1", "trace-shared-id")
    t2_spans = await harness.repository.list_spans_for_trace("t2", "trace-shared-id")
    assert len(t1_spans) == 1
    assert len(t2_spans) == 2
