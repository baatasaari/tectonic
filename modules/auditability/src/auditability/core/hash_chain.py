"""Pure hash-chain functions — no I/O, no DB, deliberately independent of
both the SQLAlchemy repository and the in-memory fake so the two can never
silently drift into computing different hashes for the same inputs (a real
correctness property this module's tests hold both implementations to, via
these same shared functions rather than two parallel reimplementations).

The construction: each entry's hash covers its own content plus the prior
entry's hash, the same "block hash chain" idea a blockchain uses minus the
distributed-consensus machinery a single-writer-per-tenant audit log has no
need for. Altering, deleting or reordering any entry breaks every
subsequent hash in that tenant's chain — `core/chain_verifier.py` proves
that deterministically.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any


def canonical_json(value: Any) -> str:
    """Deterministic JSON serialization: sorted keys, no extraneous
    whitespace, so the same logical content always hashes identically
    regardless of dict insertion order."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_entry_hash(
    *, sequence_number: int, tenant_id: str, source_module: str, event_type: str,
    occurred_at: datetime, payload: dict[str, Any], prev_hash: str | None,
) -> str:
    canonical = canonical_json({
        "sequence_number": sequence_number,
        "tenant_id": tenant_id,
        "source_module": source_module,
        "event_type": event_type,
        "occurred_at": occurred_at.isoformat(),
        "payload": payload,
        "prev_hash": prev_hash,
    })
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def extract_event_type(payload: dict[str, Any]) -> str:
    """This platform's existing callers (5 modules built before this one)
    use inconsistent keys for the same concept -- some send `event_type`,
    some send `event` -- see the module README's "Design notes vs. the
    LLD". Falls back to "unknown" rather than rejecting the write: losing
    an audit event over a naming mismatch is worse than filing it loosely
    typed."""
    value = payload.get("event_type") or payload.get("event")
    return str(value) if value else "unknown"
