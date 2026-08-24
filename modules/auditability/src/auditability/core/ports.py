"""Abstract ports this module depends on: persistence and LLM Gateway (for
natural-language query translation only -- audit-pack generation itself
needs no LLM call, it is a filtered, chronologically ordered export of
this module's own records).
"""
from __future__ import annotations

from typing import Any, Protocol

from auditability.core.domain import (
    AuditEventFilter,
    AuditEventRecord,
    AuditPackRecord,
)


class AuditabilityRepository(Protocol):
    async def append_event(
        self, *, tenant_id: str, source_module: str, event_type: str, payload: dict[str, Any],
    ) -> AuditEventRecord:
        """Atomically reads the tenant's last entry, computes the next
        sequence_number/prev_hash/entry_hash, and inserts -- this must be one
        atomic operation (a per-tenant write-serializing lock, not
        SKIP LOCKED: correctness here requires every write for a tenant to
        see the immediately preceding one, never to skip past a concurrent
        writer the way the audit-pack queue's claim does)."""
        ...

    async def list_events(self, event_filter: AuditEventFilter) -> tuple[list[AuditEventRecord], int]: ...

    async def list_events_for_chain(self, tenant_id: str) -> list[AuditEventRecord]:
        """All of a tenant's events, ordered by sequence_number ascending --
        the input `chain_verifier.verify_chain` needs."""
        ...

    async def create_audit_pack(self, record: AuditPackRecord) -> AuditPackRecord: ...

    async def update_audit_pack(self, record: AuditPackRecord) -> AuditPackRecord: ...

    async def get_audit_pack(self, tenant_id: str, pack_id: str) -> AuditPackRecord | None: ...

    async def claim_next_audit_pack(self, worker_id: str, lease_seconds: int) -> AuditPackRecord | None:
        """Same `SELECT ... FOR UPDATE SKIP LOCKED` durable-queue pattern as
        Module 17's evidence-pack worker -- see core/audit_pack_worker.py."""
        ...

    async def requeue_audit_pack_for_retry(self, pack_id: str) -> None: ...

    async def fail_exhausted_audit_packs(self, max_attempts: int) -> int: ...

    async def force_expire_stale_leases(self) -> int: ...


class LLMGatewayClient(Protocol):
    async def complete(self, *, prompt_context: dict[str, Any], tenant_id: str) -> dict[str, Any]:
        """Returns the parsed `proposal` payload; the NL Query Translator
        treats it as an untrusted candidate filter and validates it before
        it ever reaches the repository -- see core/nl_query_translator.py."""
        ...
