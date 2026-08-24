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
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[ControlMappingRecord], int]: ...

    async def create_control_event(self, record: ControlImplementationEventRecord) -> ControlImplementationEventRecord: ...

    async def list_control_events(self, tenant_id: str) -> list[ControlImplementationEventRecord]: ...

    async def create_evidence_pack(self, record: EvidencePackRecord) -> EvidencePackRecord: ...

    async def update_evidence_pack(self, record: EvidencePackRecord) -> EvidencePackRecord: ...

    async def get_evidence_pack(self, tenant_id: str, pack_id: str) -> EvidencePackRecord | None: ...


class AuditabilityClient(Protocol):
    async def query_control_events(self, tenant_id: str, control_name: str, date_range: dict | None = None) -> list[dict]:
        """Returns raw evidence records from Auditability for a control, used to enrich an
        evidence pack beyond this module's own ControlImplementationEvent rows."""
        ...
