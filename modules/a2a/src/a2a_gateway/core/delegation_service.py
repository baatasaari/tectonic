"""Delegation Service (LLD §2 sub-components): the outbound half. Fetches
(and caches) the target agent's own Agent Card, checks the requested
skill is actually one it advertises, sends the task, and persists a
local `A2ATaskRecord` so the caller can poll it — see the module README's
"Design notes vs. the LLD" for why this stays a one-shot send rather than
a background re-polling loop in this first version.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from a2a_gateway.core.domain import (
    A2ATaskRecord,
    AgentCard,
    AgentCardCacheEntry,
    SkillNotAdvertisedError,
    TaskDirection,
    TaskStatus,
    new_id,
    now,
    parse_agent_card,
)
from a2a_gateway.core.ports import A2AGatewayRepository, A2APeerClient


class DelegationService:
    def __init__(
        self, repository: A2AGatewayRepository, peer_client: A2APeerClient, *, card_cache_ttl_seconds: int = 3600,
    ) -> None:
        self._repository = repository
        self._peer_client = peer_client
        self._card_cache_ttl_seconds = card_cache_ttl_seconds

    async def delegate(
        self, *, tenant_id: str, target_agent_url: str, skill_id: str, input_message: dict[str, Any],
    ) -> A2ATaskRecord:
        card = await self._get_card(target_agent_url)
        if not card.supports(skill_id):
            raise SkillNotAdvertisedError(f"target agent at '{target_agent_url}' does not advertise skill '{skill_id}'")

        task = await self._repository.create_task(
            A2ATaskRecord(
                id=new_id(), tenant_id=tenant_id, direction=TaskDirection.OUTBOUND, peer_agent_url=target_agent_url,
                skill_id=skill_id, input_message=input_message,
            )
        )

        try:
            result = await self._peer_client.send_message(target_agent_url, skill_id=skill_id, input_message=input_message)
        except Exception as exc:  # the peer is arbitrary/third-party -- any failure lands on this task, not the caller
            return await self._repository.update_task_status(task.id, status=TaskStatus.FAILED, error=str(exc))

        status = TaskStatus(result.get("status", TaskStatus.WORKING.value))
        return await self._repository.update_task_status(
            task.id, status=status, output_artifacts=result.get("artifacts", []),
        )

    async def _get_card(self, agent_url: str) -> AgentCard:
        cached = await self._repository.get_cached_card(agent_url)
        if cached is not None and cached.expires_at > now():
            return parse_agent_card(cached.card)

        raw = await self._peer_client.fetch_agent_card(agent_url)
        await self._repository.upsert_cached_card(
            AgentCardCacheEntry(
                id=new_id(), agent_url=agent_url, card=raw,
                fetched_at=now(), expires_at=now() + timedelta(seconds=self._card_cache_ttl_seconds),
            )
        )
        return parse_agent_card(raw)
