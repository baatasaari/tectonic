"""In-memory fakes for unit tests (LLD "Deployability and testability
contract"). `InMemoryAuditabilityRepository.append_event` calls the exact
same `hash_chain.compute_entry_hash` pure function the SQLAlchemy
repository uses, so both implementations are held to producing identical
hashes for identical inputs -- not two independent reimplementations that
could silently drift apart.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from auditability.core.domain import (
    AuditEventFilter,
    AuditEventRecord,
    AuditPackRecord,
    AuditPackStatus,
    new_id,
    now,
)
from auditability.core.hash_chain import compute_entry_hash


class InMemoryAuditabilityRepository:
    def __init__(self) -> None:
        self.events: list[AuditEventRecord] = []
        self.audit_packs: dict[str, AuditPackRecord] = {}
        self._next_sequence: dict[str, int] = {}

    async def append_event(
        self, *, tenant_id: str, source_module: str, event_type: str, payload: dict[str, Any],
    ) -> AuditEventRecord:
        sequence_number = self._next_sequence.get(tenant_id, 0) + 1
        self._next_sequence[tenant_id] = sequence_number
        prior = [e for e in self.events if e.tenant_id == tenant_id]
        prev_hash = prior[-1].entry_hash if prior else None
        occurred_at = now()
        entry_hash = compute_entry_hash(
            sequence_number=sequence_number, tenant_id=tenant_id, source_module=source_module,
            event_type=event_type, occurred_at=occurred_at, payload=payload, prev_hash=prev_hash,
        )
        record = AuditEventRecord(
            id=new_id(), tenant_id=tenant_id, source_module=source_module, event_type=event_type,
            payload=payload, sequence_number=sequence_number, entry_hash=entry_hash, prev_hash=prev_hash,
            occurred_at=occurred_at,
        )
        self.events.append(record)
        return record

    async def list_events(self, event_filter: AuditEventFilter) -> tuple[list[AuditEventRecord], int]:
        results = [e for e in self.events if e.tenant_id == event_filter.tenant_id]
        if event_filter.event_type is not None:
            results = [e for e in results if e.event_type == event_filter.event_type]
        if event_filter.source_module is not None:
            results = [e for e in results if e.source_module == event_filter.source_module]
        if event_filter.control_name is not None:
            results = [e for e in results if e.payload.get("control_name") == event_filter.control_name]
        if event_filter.occurred_after is not None:
            results = [e for e in results if e.occurred_at >= event_filter.occurred_after]
        if event_filter.occurred_before is not None:
            results = [e for e in results if e.occurred_at <= event_filter.occurred_before]
        results = sorted(results, key=lambda e: e.sequence_number, reverse=True)
        total = len(results)
        return results[event_filter.offset:event_filter.offset + event_filter.limit], total

    async def list_events_for_chain(self, tenant_id: str) -> list[AuditEventRecord]:
        return sorted(
            (e for e in self.events if e.tenant_id == tenant_id), key=lambda e: e.sequence_number,
        )

    async def create_audit_pack(self, record: AuditPackRecord) -> AuditPackRecord:
        self.audit_packs[record.id] = record
        return record

    async def update_audit_pack(self, record: AuditPackRecord) -> AuditPackRecord:
        self.audit_packs[record.id] = record
        return record

    async def get_audit_pack(self, tenant_id: str, pack_id: str) -> AuditPackRecord | None:
        pack = self.audit_packs.get(pack_id)
        if pack is None or pack.tenant_id != tenant_id:
            return None
        return pack

    async def claim_next_audit_pack(self, worker_id: str, lease_seconds: int) -> AuditPackRecord | None:
        moment = now()
        candidates = sorted(
            (
                p for p in self.audit_packs.values()
                if p.status == AuditPackStatus.GENERATING
                and (p.lease_expires_at is None or p.lease_expires_at < moment)
            ),
            key=lambda p: p.created_at,
        )
        if not candidates:
            return None
        pack = candidates[0]
        pack.worker_id = worker_id
        pack.attempts += 1
        pack.lease_expires_at = moment + timedelta(seconds=lease_seconds)
        return pack

    async def requeue_audit_pack_for_retry(self, pack_id: str) -> None:
        pack = self.audit_packs.get(pack_id)
        if pack is None:
            return
        pack.status = AuditPackStatus.GENERATING
        pack.lease_expires_at = None

    async def fail_exhausted_audit_packs(self, max_attempts: int) -> int:
        count = 0
        for p in self.audit_packs.values():
            if p.status == AuditPackStatus.GENERATING and p.attempts >= max_attempts:
                p.status = AuditPackStatus.FAILED
                p.last_error = f"exceeded max attempts ({max_attempts})"
                count += 1
        return count

    async def force_expire_stale_leases(self) -> int:
        moment = now()
        count = 0
        for p in self.audit_packs.values():
            if p.status == AuditPackStatus.GENERATING and p.lease_expires_at is not None and p.lease_expires_at > moment:
                p.lease_expires_at = moment
                count += 1
        return count


class StubLLMGatewayClient:
    def __init__(self, proposal: dict | None = None) -> None:
        self.calls: list[dict] = []
        self._proposal = proposal if proposal is not None else {}

    async def complete(self, *, prompt_context: dict, tenant_id: str) -> dict:
        self.calls.append({"prompt_context": prompt_context, "tenant_id": tenant_id})
        return self._proposal


__all__ = ["InMemoryAuditabilityRepository", "StubLLMGatewayClient"]
