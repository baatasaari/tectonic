"""Legal Hold Service (memory governance foundation): place/release a
hold on (tenant_id, scope) that blocks erasure while active. See
LegalHoldRecord's own docstring in core/domain.py and
ForgettingEngine.execute's own docstring for the actual enforcement --
this service only manages the hold records themselves.
"""
from __future__ import annotations

from long_term_memory.core.domain import LegalHoldNotFoundError, LegalHoldRecord, new_id
from long_term_memory.core.ports import LongTermMemoryRepository


class LegalHoldService:
    def __init__(self, repository: LongTermMemoryRepository) -> None:
        self._repository = repository

    async def place(self, *, tenant_id: str, scope: str, reason: str, placed_by: str = "") -> LegalHoldRecord:
        # Idempotent, same reasoning as ConsentService.grant: placing a hold
        # on a scope already under one is a no-op restating a fact already
        # true, not a second concurrent hold two get_active_legal_hold
        # lookups would then have to reconcile.
        existing = await self._repository.get_active_legal_hold(tenant_id, scope)
        if existing is not None:
            return existing

        record = LegalHoldRecord(id=new_id(), tenant_id=tenant_id, scope=scope, reason=reason, placed_by=placed_by)
        return await self._repository.create_legal_hold(record)

    async def release(self, *, tenant_id: str, hold_id: str) -> LegalHoldRecord:
        record = await self._repository.release_legal_hold(tenant_id, hold_id)
        if record is None:
            raise LegalHoldNotFoundError(hold_id)
        return record

    async def list_for_scope(self, tenant_id: str, scope: str) -> list[LegalHoldRecord]:
        return await self._repository.list_legal_holds(tenant_id, scope)

    async def is_active(self, tenant_id: str, scope: str) -> bool:
        return await self._repository.get_active_legal_hold(tenant_id, scope) is not None
