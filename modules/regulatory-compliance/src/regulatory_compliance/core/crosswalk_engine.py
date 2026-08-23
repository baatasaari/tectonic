"""Crosswalk Engine (LLD §2 sub-components): maps a control implementation
to relevant clauses across every framework a tenant has enabled, then
records the implementation event.
"""
from __future__ import annotations

from regulatory_compliance.core.domain import (
    ControlImplementationEventRecord,
    MappingResult,
    new_id,
)
from regulatory_compliance.core.ports import RegulatoryComplianceRepository


class CrosswalkEngine:
    def __init__(self, repository: RegulatoryComplianceRepository) -> None:
        self._repository = repository

    async def map_control(
        self, tenant_id: str, control_name: str, source_module: str, evidence_ref: str,
    ) -> list[MappingResult]:
        """Note: deliberately does not filter on `ControlMapping.deprecated` here — a
        tenant's `FrameworkProfile.version` pins them to a specific mapping-table version,
        and matching that exact version is what "existing tenants continue on prior version
        until they opt in" (LLD §Level 3) means in practice. `deprecated` only matters when
        no specific version is pinned (see `CoverageCalculator.coverage`)."""
        profiles = await self._repository.list_framework_profiles(tenant_id, enabled_only=True)
        results: list[MappingResult] = []
        for profile in profiles:
            mappings = await self._repository.list_control_mappings(
                control_name=control_name, framework_name=profile.framework_name,
            )
            for m in mappings:
                if m.framework_version != profile.version:
                    continue
                results.append(
                    MappingResult(control_name=control_name, framework_name=m.framework_name, clause_references=m.clause_references)
                )

        event = ControlImplementationEventRecord(
            id=new_id(), tenant_id=tenant_id, control_name=control_name, source_module=source_module,
            evidence_ref=evidence_ref,
        )
        await self._repository.create_control_event(event)
        return results


class CoverageCalculator:
    def __init__(self, repository: RegulatoryComplianceRepository) -> None:
        self._repository = repository

    async def coverage(self, tenant_id: str, framework_name: str) -> tuple[float, list[str]]:
        """Returns (coverage_percentage, gaps) — gaps being required controls (per the
        framework's currently-enabled mapping version) with no recorded implementation event."""
        profile = await self._repository.get_framework_profile(tenant_id, framework_name)
        version = profile.version if profile else None

        mappings = await self._repository.list_control_mappings(framework_name=framework_name)
        # Pinned to a version (the common case): match it exactly, deprecated or not, same
        # reasoning as CrosswalkEngine.map_control. No profile yet: fall back to whatever
        # the feed currently considers non-deprecated, i.e. the latest published version.
        required = sorted({
            m.control_name for m in mappings
            if (version is not None and m.framework_version == version) or (version is None and not m.deprecated)
        })
        if not required:
            return 100.0, []

        events = await self._repository.list_control_events(tenant_id)
        implemented = {e.control_name for e in events}
        gaps = [c for c in required if c not in implemented]
        coverage_pct = (len(required) - len(gaps)) / len(required) * 100.0
        return coverage_pct, gaps
