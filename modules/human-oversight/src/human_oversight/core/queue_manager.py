"""Approval Queue Manager (LLD §2 sub-components): accepts escalation
requests, manages queue state, claiming, timeout.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from human_oversight.core.domain import (
    OversightRequestRecord,
    RequestNotClaimableError,
    RequestNotFoundError,
    RequestStatus,
    new_id,
    now,
)
from human_oversight.core.ports import HumanOversightRepository


class ApprovalQueueManager:
    def __init__(self, repository: HumanOversightRepository, default_timeout_seconds: int) -> None:
        self._repository = repository
        self._default_timeout_seconds = default_timeout_seconds

    async def enqueue(
        self, *, tenant_id: str, requesting_module: str, requesting_ref: str, context: dict[str, Any],
        priority: str = "medium", timeout_seconds: int | None = None,
    ) -> OversightRequestRecord:
        timeout = timeout_seconds or self._default_timeout_seconds
        record = OversightRequestRecord(
            id=new_id(), tenant_id=tenant_id, requesting_module=requesting_module, requesting_ref=requesting_ref,
            context=context, priority=priority, expires_at=now() + timedelta(seconds=timeout),
        )
        return await self._repository.create_request(record)

    async def claim(self, tenant_id: str, request_id: str, claimed_by: str) -> OversightRequestRecord:
        request = await self._repository.get_request(tenant_id, request_id)
        if request is None:
            raise RequestNotFoundError(request_id)
        if request.status != RequestStatus.PENDING:
            raise RequestNotClaimableError(request_id, request.status.value)
        request.status = RequestStatus.CLAIMED
        request.claimed_by = claimed_by
        return await self._repository.update_request(request)

    async def sweep_expired(self, tenant_id: str) -> list[OversightRequestRecord]:
        overdue = await self._repository.list_pending_expired(tenant_id, now())
        expired = []
        for request in overdue:
            request.status = RequestStatus.EXPIRED
            expired.append(await self._repository.update_request(request))
        return expired
