"""Consent Service (memory governance foundation, independent
architecture assessment's own finding -- "no ... consent ... legal-hold
gap, currently zero coverage"): grant/revoke consent for (tenant_id,
scope, purpose), with a durable ConsentRecord audit trail. See that
record's own docstring in core/domain.py for why revoke updates the
same row rather than adding a second one, and MemoryService.query's own
docstring for how a revoked/missing consent actually affects retrieval.
"""
from __future__ import annotations

from long_term_memory.core.domain import (
    ConsentBasis,
    ConsentRecord,
    ConsentRecordNotFoundError,
    new_id,
)
from long_term_memory.core.ports import LongTermMemoryRepository


class ConsentService:
    def __init__(self, repository: LongTermMemoryRepository) -> None:
        self._repository = repository

    async def grant(
        self, *, tenant_id: str, scope: str, purpose: str, basis: ConsentBasis, granted_by: str = "",
    ) -> ConsentRecord:
        # Idempotent the same way RoleBindingService.grant is: granting
        # consent that's already active for this exact (scope, purpose) is
        # a no-op restating a fact already true, not a new audit-worthy
        # event -- return the existing record rather than writing a
        # duplicate active row two get_active_consent lookups would then
        # have to choose between.
        existing = await self._repository.get_active_consent(tenant_id, scope, purpose)
        if existing is not None:
            return existing

        record = ConsentRecord(
            id=new_id(), tenant_id=tenant_id, scope=scope, purpose=purpose, basis=basis, granted_by=granted_by,
        )
        return await self._repository.create_consent_record(record)

    async def revoke(self, *, tenant_id: str, consent_id: str) -> ConsentRecord:
        record = await self._repository.revoke_consent(tenant_id, consent_id)
        if record is None:
            raise ConsentRecordNotFoundError(consent_id)
        return record

    async def list_for_scope(self, tenant_id: str, scope: str) -> list[ConsentRecord]:
        return await self._repository.list_consents(tenant_id, scope)

    async def is_active(self, tenant_id: str, scope: str, purpose: str) -> bool:
        return await self._repository.get_active_consent(tenant_id, scope, purpose) is not None
