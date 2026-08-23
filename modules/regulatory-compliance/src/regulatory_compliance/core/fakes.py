"""In-memory fakes for unit tests (LLD "Deployability and testability
contract": crosswalk logic tested purely against fixture mapping tables,
independent of any other module).
"""
from __future__ import annotations

from regulatory_compliance.core.domain import (
    ControlImplementationEventRecord,
    ControlMappingRecord,
    EvidencePackRecord,
    FrameworkProfileRecord,
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
    ) -> list[ControlMappingRecord]:
        results = list(self.control_mappings.values())
        if control_name is not None:
            results = [m for m in results if m.control_name == control_name]
        if framework_name is not None:
            results = [m for m in results if m.framework_name == framework_name]
        return results

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


class StubAuditabilityClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def query_control_events(self, tenant_id: str, control_name: str, date_range: dict | None = None) -> list[dict]:
        self.calls.append({"tenant_id": tenant_id, "control_name": control_name, "date_range": date_range})
        return []
