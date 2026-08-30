"""Pure-function tests for the hash-chain primitives (core/hash_chain.py)."""
from __future__ import annotations

from datetime import UTC, datetime

from auditability.core.hash_chain import canonical_json, compute_entry_hash, extract_event_type


def _hash(**overrides):
    kwargs = {
        "sequence_number": 1, "tenant_id": "t1", "source_module": "workflow-engine", "event_type": "handoff",
        "occurred_at": datetime(2026, 1, 1, tzinfo=UTC), "payload": {"a": 1}, "prev_hash": None,
    }
    kwargs.update(overrides)
    return compute_entry_hash(**kwargs)


def test_same_inputs_produce_the_same_hash():
    assert _hash() == _hash()


def test_different_payload_produces_a_different_hash():
    assert _hash(payload={"a": 1}) != _hash(payload={"a": 2})


def test_different_prev_hash_produces_a_different_hash():
    assert _hash(prev_hash=None) != _hash(prev_hash="some-prior-hash")


def test_different_sequence_number_produces_a_different_hash():
    assert _hash(sequence_number=1) != _hash(sequence_number=2)


def test_canonical_json_is_insensitive_to_key_order():
    assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})


def test_extract_event_type_prefers_event_type_key():
    assert extract_event_type({"event_type": "x", "event": "y"}) == "x"


def test_extract_event_type_falls_back_to_event_key():
    assert extract_event_type({"event": "y"}) == "y"


def test_extract_event_type_falls_back_to_unknown_when_neither_key_present():
    assert extract_event_type({"tenant_id": "t1"}) == "unknown"
