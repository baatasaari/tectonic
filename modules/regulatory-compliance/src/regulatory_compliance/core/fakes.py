"""In-memory fakes for unit tests (LLD "Deployability and testability
contract": crosswalk logic tested purely against fixture mapping tables,
independent of any other module).
"""
from __future__ import annotations

from datetime import timedelta

from regulatory_compliance.core.domain import (
    ControlImplementationEventRecord,
    ControlMappingRecord,
    EvidencePackRecord,
    EvidencePackStatus,
    FrameworkProfileRecord,
    now,
)


class InMemoryRegulatoryComplianceRepository:
    def __init__(self) -> None:
        self.framework_profiles: dict[str, FrameworkProfileRecord] = {}
        self.control_mappings: dict[str, ControlMappingRecord] = {}
        self.control_events: list[ControlImplementationEventRecord] = []
        self.evidence_packs: dict[str, EvidencePackRecord] = {}

    async def create_framework_profile(self, record: FrameworkProfileRecord) -> FrameworkProfileRecord:
        self.framework_profiles[record.id] = record
        return record

    async def get_framework_profile(self, tenant_id: str, framework_name: str) -> FrameworkProfileRecord | None:
        for p in self.framework_profiles.values():
            if p.tenant_id == tenant_id and p.framework_name == framework_name:
                return p
        return None

    async def list_framework_profiles(self, tenant_id: str, *, enabled_only: bool = False) -> list[FrameworkProfileRecord]:
        return [
            p for p in self.framework_profiles.values()
            if p.tenant_id == tenant_id and (not enabled_only or p.enabled)
        ]

    async def upsert_control_mapping(self, record: ControlMappingRecord) -> ControlMappingRecord:
        for existing in self.control_mappings.values():
            if (
                existing.control_name == record.control_name
                and existing.framework_name == record.framework_name
                and existing.framework_version == record.framework_version
                and not existing.deprecated
            ):
                existing.clause_references = record.clause_references
                existing.mapping_rationale = record.mapping_rationale
                return existing
        self.control_mappings[record.id] = record
        return record

    async def deprecate_control_mappings(self, control_name: str, framework_name: str, older_than_version: str) -> int:
        count = 0
        for m in self.control_mappings.values():
            if m.control_name == control_name and m.framework_name == framework_name and m.framework_version != older_than_version and not m.deprecated:
                m.deprecated = True
                count += 1
        return count

    async def list_control_mappings(
        self, *, control_name: str | None = None, framework_name: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[ControlMappingRecord], int]:
        results = list(self.control_mappings.values())
        if control_name is not None:
            results = [m for m in results if m.control_name == control_name]
        if framework_name is not None:
            results = [m for m in results if m.framework_name == framework_name]
        # id ascending, matching the SQL repository's ORDER BY id (no timestamp column exists
        # on ControlMapping to order by instead).
        results = sorted(results, key=lambda m: m.id)
        return results[offset:offset + limit], len(results)

    async def create_control_event(self, record: ControlImplementationEventRecord) -> ControlImplementationEventRecord:
        self.control_events.append(record)
        return record

    async def list_control_events(self, tenant_id: str) -> list[ControlImplementationEventRecord]:
        return [e for e in self.control_events if e.tenant_id == tenant_id]

    async def create_evidence_pack(self, record: EvidencePackRecord) -> EvidencePackRecord:
        self.evidence_packs[record.id] = record
        return record

    async def update_evidence_pack(self, record: EvidencePackRecord) -> EvidencePackRecord:
        self.evidence_packs[record.id] = record
        return record

    async def get_evidence_pack(self, tenant_id: str, pack_id: str) -> EvidencePackRecord | None:
        pack = self.evidence_packs.get(pack_id)
        if pack is None or pack.tenant_id != tenant_id:
            return None
        return pack

    async def claim_next_evidence_pack(self, worker_id: str, lease_seconds: int) -> EvidencePackRecord | None:
        moment = now()
        candidates = sorted(
            (
                p for p in self.evidence_packs.values()
                if p.status == EvidencePackStatus.GENERATING
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

    async def requeue_evidence_pack_for_retry(self, pack_id: str) -> None:
        pack = self.evidence_packs.get(pack_id)
        if pack is None:
            return
        pack.status = EvidencePackStatus.GENERATING
        pack.lease_expires_at = None

    async def fail_exhausted_evidence_packs(self, max_attempts: int) -> int:
        count = 0
        for p in self.evidence_packs.values():
            if p.status == EvidencePackStatus.GENERATING and p.attempts >= max_attempts:
                p.status = EvidencePackStatus.FAILED
                p.last_error = f"exceeded max attempts ({max_attempts})"
                count += 1
        return count

    async def force_expire_stale_leases(self) -> int:
        moment = now()
        count = 0
        for p in self.evidence_packs.values():
            if p.status == EvidencePackStatus.GENERATING and p.lease_expires_at is not None and p.lease_expires_at > moment:
                p.lease_expires_at = moment
                count += 1
        return count


class StubAuditabilityClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def query_control_events(self, tenant_id: str, control_name: str, date_range: dict | None = None) -> list[dict]:
        self.calls.append({"tenant_id": tenant_id, "control_name": control_name, "date_range": date_range})
        return []
