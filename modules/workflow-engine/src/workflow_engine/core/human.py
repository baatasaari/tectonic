"""Human Approval Handler (LLD §2.2): raises and tracks approval requests.

Wired to ADK's native human-in-the-loop node type in production; here it
persists an ApprovalRequest and notifies the Human Oversight module through
its port, then returns control to the scheduler with `AWAITING_APPROVAL` —
the scheduler is responsible for pausing the instance. Resolution comes back
asynchronously via the `/instances/{id}/approvals/{approval_id}/callback`
API endpoint (LLD §3.3), not by this handler blocking.
"""
from __future__ import annotations

from workflow_engine.core.domain import ApprovalRequestRecord, ApprovalStatus, new_id
from workflow_engine.core.ports import HumanOversightClient, WorkflowRepository


class HumanApprovalHandler:
    def __init__(self, repository: WorkflowRepository, human_oversight: HumanOversightClient) -> None:
        self.repository = repository
        self.human_oversight = human_oversight

    async def request_approval(
        self, *, step_execution_id: str, instance_id: str, context: dict, tenant_id: str
    ) -> ApprovalRequestRecord:
        record = ApprovalRequestRecord(id=new_id(), step_execution_id=step_execution_id)
        record = await self.repository.create_approval_request(record)

        ref_id = await self.human_oversight.request_approval(
            approval_request_id=record.id,
            step_execution_id=step_execution_id,
            instance_id=instance_id,
            context=context,
            tenant_id=tenant_id,
        )
        record.human_oversight_ref_id = ref_id
        return await self.repository.update_approval_request(record)

    async def resolve(self, approval_id: str, decision: str, resolved_by: str) -> ApprovalRequestRecord:
        from workflow_engine.core.domain import now

        record = await self.repository.get_approval_request(approval_id)
        if record is None:
            raise LookupError(approval_id)
        record.status = ApprovalStatus.APPROVED if decision == "approved" else ApprovalStatus.REJECTED
        record.resolved_at = now()
        return await self.repository.update_approval_request(record)
