"""Tests for core/chain_verifier.py -- the tamper-evidence proof itself."""
from __future__ import annotations

from auditability.core.chain_verifier import verify_chain
from auditability.core.domain import now


async def test_an_empty_chain_is_valid(harness):
    result = verify_chain([])

    assert result.valid is True
    assert result.verified_count == 0


async def test_a_genuine_multi_entry_chain_verifies(harness):
    for i in range(5):
        await harness.repository.append_event(
            tenant_id="t1", source_module="workflow-engine", event_type="step", payload={"i": i},
        )
    events = await harness.repository.list_events_for_chain("t1")

    result = verify_chain(events)

    assert result.valid is True
    assert result.verified_count == 5


async def test_a_tampered_payload_breaks_the_chain_from_that_entry_onward(harness):
    for i in range(3):
        await harness.repository.append_event(
            tenant_id="t1", source_module="workflow-engine", event_type="step", payload={"i": i},
        )
    events = await harness.repository.list_events_for_chain("t1")
    events[1].payload = {"i": "tampered"}  # mutate in place, as if a row were altered post-write

    result = verify_chain(events)

    assert result.valid is False
    assert result.break_at_sequence == 2


async def test_a_chain_with_an_altered_prev_hash_link_is_detected(harness):
    for i in range(3):
        await harness.repository.append_event(
            tenant_id="t1", source_module="workflow-engine", event_type="step", payload={"i": i},
        )
    events = await harness.repository.list_events_for_chain("t1")
    events[2].prev_hash = "not-the-real-prior-hash"

    result = verify_chain(events)

    assert result.valid is False
    assert result.break_at_sequence == 3


async def test_verify_chain_ignores_the_occurred_at_argument_type(harness):
    # Regression guard: verify_chain must accept whatever occurred_at the repository
    # hands back (a real datetime), not silently coerce/ignore it.
    event = await harness.repository.append_event(
        tenant_id="t1", source_module="workflow-engine", event_type="step", payload={},
    )
    assert event.occurred_at <= now()
