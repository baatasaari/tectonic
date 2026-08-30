"""Chain Verifier (LLD §2 sub-components): walks a tenant's event chain in
sequence order and recomputes each entry's hash independently, reporting
the first break if the stored `entry_hash`/`prev_hash` no longer matches
what the content actually hashes to. A pure function over already-fetched
rows -- no DB/HTTP dependency, so this is the one place a tampering claim
gets proven, not just asserted.
"""
from __future__ import annotations

from auditability.core.domain import AuditEventRecord, ChainVerificationResult
from auditability.core.hash_chain import compute_entry_hash


def verify_chain(events: list[AuditEventRecord]) -> ChainVerificationResult:
    """`events` must already be ordered by `sequence_number` ascending."""
    prev_hash: str | None = None
    for event in events:
        expected = compute_entry_hash(
            sequence_number=event.sequence_number, tenant_id=event.tenant_id,
            source_module=event.source_module, event_type=event.event_type,
            occurred_at=event.occurred_at, payload=event.payload, prev_hash=prev_hash,
        )
        if expected != event.entry_hash or event.prev_hash != prev_hash:
            return ChainVerificationResult(
                valid=False, verified_count=event.sequence_number - 1, break_at_sequence=event.sequence_number,
            )
        prev_hash = event.entry_hash

    return ChainVerificationResult(valid=True, verified_count=len(events))
