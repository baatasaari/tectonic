"""In-memory fakes for unit tests (LLD "Deployability and testability
contract")."""
from __future__ import annotations

from typing import Any

from a2a_gateway.core.domain import (
    A2AAccessPolicyRecord,
    A2ATaskRecord,
    AgentCardCacheEntry,
    TaskDirection,
    TaskStatus,
    now,
)


class InMemoryA2AGatewayRepository:
    def __init__(self) -> None:
        self.tasks: dict[str, A2ATaskRecord] = {}
        self.access_policies: dict[tuple[str, str], A2AAccessPolicyRecord] = {}
        self.card_cache: dict[str, AgentCardCacheEntry] = {}

    async def create_task(self, record: A2ATaskRecord) -> A2ATaskRecord:
        self.tasks[record.id] = record
        return record

    async def get_task(self, task_id: str) -> A2ATaskRecord | None:
        return self.tasks.get(task_id)

    async def update_task_status(
        self, task_id: str, *, status: TaskStatus, output_artifacts: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> A2ATaskRecord:
        task = self.tasks[task_id]
        task.status = TaskStatus(status)
        if output_artifacts is not None:
            task.output_artifacts = output_artifacts
        if error is not None:
            task.error = error
        task.updated_at = now()
        return task

    async def list_tasks(
        self, *, tenant_id: str | None = None, direction: TaskDirection | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[A2ATaskRecord], int]:
        results = list(self.tasks.values())
        if tenant_id is not None:
            results = [t for t in results if t.tenant_id == tenant_id]
        if direction is not None:
            results = [t for t in results if t.direction == direction]
        results = sorted(results, key=lambda t: t.created_at)
        return results[offset:offset + limit], len(results)

    async def upsert_access_policy(self, record: A2AAccessPolicyRecord) -> A2AAccessPolicyRecord:
        self.access_policies[(record.caller_agent_id, record.tenant_id)] = record
        return record

    async def get_access_policy(self, caller_agent_id: str, tenant_id: str) -> A2AAccessPolicyRecord | None:
        return self.access_policies.get((caller_agent_id, tenant_id))

    async def get_cached_card(self, agent_url: str) -> AgentCardCacheEntry | None:
        return self.card_cache.get(agent_url)

    async def upsert_cached_card(self, entry: AgentCardCacheEntry) -> AgentCardCacheEntry:
        self.card_cache[entry.agent_url] = entry
        return entry


class StubA2APeerClient:
    def __init__(
        self, *, card: dict[str, Any] | None = None, send_result: dict[str, Any] | None = None,
        send_error: Exception | None = None,
    ) -> None:
        self.calls: list[dict] = []
        self._card = card if card is not None else {"name": "peer", "description": "", "url": "", "skills": []}
        self._send_result = send_result
        self._send_error = send_error

    async def fetch_agent_card(self, agent_url: str) -> dict[str, Any]:
        self.calls.append({"op": "fetch_agent_card", "agent_url": agent_url})
        return self._card

    async def send_message(self, agent_url: str, *, skill_id: str, input_message: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"op": "send_message", "agent_url": agent_url, "skill_id": skill_id})
        if self._send_error is not None:
            raise self._send_error
        if self._send_result is not None:
            return self._send_result
        return {"status": "completed", "artifacts": [{"ok": True}]}


class StubWorkflowEngineClient:
    def __init__(self, *, response: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self._response = response
        self._error = error

    async def start_instance(self, *, definition_id: str, tenant_id: str, initial_context: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"definition_id": definition_id, "tenant_id": tenant_id, "initial_context": initial_context})
        if self._error is not None:
            raise self._error
        if self._response is not None:
            return self._response
        return {"id": "wf-instance-1", "status": "running", "trace_id": "trace-1"}


__all__ = ["InMemoryA2AGatewayRepository", "StubA2APeerClient", "StubWorkflowEngineClient"]
