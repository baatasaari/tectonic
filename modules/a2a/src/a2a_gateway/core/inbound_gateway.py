"""Inbound Task Gateway (LLD §2 sub-components, §Level 3 "Sequence: an
inbound message/send"): the one place an inbound task from an external
A2A caller actually gets enforced against the Access Policy Engine and
dispatched into Workflow Engine (Module 1) — this module's job stops at
accept/reject/track; Workflow Engine is the real execution engine.
"""
from __future__ import annotations

from typing import Any

from a2a_gateway.core.access_policy_engine import AccessPolicyEngine
from a2a_gateway.core.domain import (
    A2ATaskRecord,
    TaskDirection,
    TaskStatus,
    UnknownSkillError,
    new_id,
)
from a2a_gateway.core.ports import A2AGatewayRepository, WorkflowEngineClient


class InboundGateway:
    def __init__(
        self, repository: A2AGatewayRepository, workflow_client: WorkflowEngineClient,
        skill_definition_map: dict[str, str],
    ) -> None:
        self._repository = repository
        self._workflow_client = workflow_client
        self._skill_definition_map = skill_definition_map

    async def accept(
        self, *, tenant_id: str, caller_agent_id: str, peer_agent_url: str, skill_id: str,
        input_message: dict[str, Any],
    ) -> A2ATaskRecord:
        """Raises AccessDeniedError or UnknownSkillError; returns the
        persisted task (status `working` on a successful dispatch, or
        `failed` if Workflow Engine itself rejected the start) otherwise.
        """
        await AccessPolicyEngine(self._repository).authorize(
            caller_agent_id=caller_agent_id, tenant_id=tenant_id, skill_id=skill_id,
        )

        definition_id = self._skill_definition_map.get(skill_id)
        if definition_id is None:
            raise UnknownSkillError(f"skill '{skill_id}' is not published by this agent")

        task = await self._repository.create_task(
            A2ATaskRecord(
                id=new_id(), tenant_id=tenant_id, direction=TaskDirection.INBOUND, peer_agent_url=peer_agent_url,
                skill_id=skill_id, input_message=input_message,
            )
        )

        try:
            result = await self._workflow_client.start_instance(
                definition_id=definition_id, tenant_id=tenant_id, initial_context=input_message,
            )
        except Exception as exc:
            return await self._repository.update_task_status(task.id, status=TaskStatus.FAILED, error=str(exc))

        return await self._repository.update_task_status(
            task.id, status=TaskStatus.WORKING,
            output_artifacts=[{"workflow_instance_id": result.get("id"), "trace_id": result.get("trace_id")}],
        )
