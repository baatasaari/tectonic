"""Abstract ports this module depends on: persistence and Auditability
(the platform's evidence source of record).
"""
from __future__ import annotations

from typing import Protocol

from regulatory_compliance.core.domain import (
    ControlImplementationEventRecord,
    ControlMappingRecord,
    EvidencePackRecord,
    FrameworkProfileRecord,
)


class RegulatoryComplianceRepository(Protocol):
    async def create_framework_profile(self, record: FrameworkProfileRecord) -> FrameworkProfileRecord: ...

    async def get_framework_profile(self, tenant_id: str, framework_name: str) -> FrameworkProfileRecord | None: ...

    async def list_framework_profiles(self, tenant_id: str, *, enabled_only: bool = False) -> list[FrameworkProfileRecord]: ...

    async def upsert_control_mapping(self, record: ControlMappingRecord) -> ControlMappingRecord: ...

    async def deprecate_control_mappings(self, control_name: str, framework_name: str, older_than_version: str) -> int: ...

    async def list_control_mappings(
        self, *, control_name: str | None = None, framework_name: str | None = None,
    ) -> list[ControlMappingRecord]: ...

    async def create_control_event(self, record: ControlImplementationEventRecord) -> ControlImplementationEventRecord: ...

    async def list_control_events(self, tenant_id: str) -> list[ControlImplementationEventRecord]: ...

    async def create_evidence_pack(self, record: EvidencePackRecord) -> EvidencePackRecord: ...

    async def update_evidence_pack(self, record: EvidencePackRecord) -> EvidencePackRecord: ...

    async def get_evidence_pack(self, tenant_id: str, pack_id: str) -> EvidencePackRecord | None: ...

    async def claim_next_evidence_pack(
        self, worker_id: str, lease_seconds: int
    ) -> EvidencePackRecord | None:
        """Atomically claims the oldest pending (or lease-expired) `generating` pack for
        this worker to process, incrementing its attempt count. Returns None if there's
        nothing claimable right now. Must never let two callers claim the same row."""
        ...

    async def requeue_evidence_pack_for_retry(self, pack_id: str) -> None:
        """Puts a failed-but-retryable pack back to `generating` with its lease cleared,
        so it's immediately claimable again on the next poll rather than waiting out a
        lease it no longer holds."""
        ...

    async def fail_exhausted_evidence_packs(self, max_attempts: int) -> int:
        """Marks any `generating` pack that has exhausted its retry budget as `failed`
        (poison-pill handling), so it stops being repeatedly reclaimed and retried
        forever. Returns the number of packs failed."""
        ...

    async def force_expire_stale_leases(self) -> int:
        """Startup recovery sweep: force-expires every currently-held lease so any job
        left mid-flight by a previous, now-dead process instance becomes immediately
        claimable again, rather than waiting out the remainder of its lease window.
        Returns the number of leases expired."""
        ...


class AuditabilityClient(Protocol):
    async def query_control_events(self, tenant_id: str, control_name: str, date_range: dict | None = None) -> list[dict]:
        """Returns raw evidence records from Auditability for a control, used to enrich an
        evidence pack beyond this module's own ControlImplementationEvent rows."""
        ...
