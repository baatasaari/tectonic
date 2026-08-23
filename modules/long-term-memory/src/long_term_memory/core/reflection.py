"""Reflection Loop (LLD §2 sub-components) — deviation from the LLD's
ADK 2.0 `Agent` reflection pattern; see the module README's "Design
notes vs. the LLD". Generates and stores reflections on failed/corrected
interactions, triggered by Evaluation Framework signals.
"""
from __future__ import annotations

from long_term_memory.core.domain import ReflectionEntryRecord, new_id
from long_term_memory.core.ports import LLMGatewayClient, LongTermMemoryRepository


class ReflectionLoop:
    def __init__(self, repository: LongTermMemoryRepository, llm_gateway: LLMGatewayClient) -> None:
        self._repository = repository
        self._llm_gateway = llm_gateway

    async def generate(
        self, tenant_id: str, agent_ref: str, triggering_interaction_ref: str, context: str,
    ) -> ReflectionEntryRecord:
        content = await self._llm_gateway.reflect(context, tenant_id)
        entry = ReflectionEntryRecord(
            id=new_id(), tenant_id=tenant_id, agent_ref=agent_ref,
            triggering_interaction_ref=triggering_interaction_ref, reflection_content=content,
        )
        return await self._repository.create_reflection(entry)

    async def list_for_agent(self, tenant_id: str, agent_ref: str) -> list[ReflectionEntryRecord]:
        return await self._repository.list_reflections(tenant_id, agent_ref)
