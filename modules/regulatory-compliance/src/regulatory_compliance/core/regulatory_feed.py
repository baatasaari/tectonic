"""Regulatory Feed Manager (LLD §2 sub-components, §Level 3 "Sequence:
regulatory feed update"): manages versioned framework mapping tables and
applies updates as regulations change, without a platform rebuild — the
"living regulatory feed" claim.
"""
from __future__ import annotations

from typing import Any

from regulatory_compliance.core.domain import ControlMappingRecord, new_id
from regulatory_compliance.core.mapping_data import DEFAULT_MAPPINGS
from regulatory_compliance.core.ports import RegulatoryComplianceRepository


class RegulatoryFeedManager:
    def __init__(self, repository: RegulatoryComplianceRepository) -> None:
        self._repository = repository

    async def seed_defaults(self) -> int:
        """Idempotently loads the bundled default crosswalk table. Safe to call on every
        startup — upserting is a no-op once a mapping already exists for that
        (control_name, framework_name, framework_version) triple."""
        return await self.publish(DEFAULT_MAPPINGS, deprecate_prior=False)

    async def publish(self, mappings: list[dict[str, Any]], *, deprecate_prior: bool = True) -> int:
        """Publishes a new (or updated) mapping table. Per the LLD's own sequence note:
        existing tenants continue on the prior framework_version until they opt in — a
        published update marks the prior version's rows deprecated=True, it never deletes
        them, so an in-flight audit cycle never sees its evidence trail change shape."""
        count = 0
        for raw in mappings:
            if deprecate_prior:
                await self._repository.deprecate_control_mappings(
                    raw["control_name"], raw["framework_name"], raw["framework_version"],
                )
            record = ControlMappingRecord(
                id=new_id(), control_name=raw["control_name"], framework_name=raw["framework_name"],
                framework_version=raw["framework_version"], clause_references=list(raw["clause_references"]),
                mapping_rationale=raw["mapping_rationale"], deprecated=False,
            )
            await self._repository.upsert_control_mapping(record)
            count += 1
        return count
