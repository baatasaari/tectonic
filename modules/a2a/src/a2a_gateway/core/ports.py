"""Abstract ports this module depends on: persistence, the outbound peer
client (calls to an arbitrary external A2A agent), and the Workflow
Engine client (dispatches an accepted inbound task into this platform's
own execution engine).
"""
from __future__ import annotations

from typing import Any, Protocol

from a2a_gateway.core.domain import (
    A2AAccessPolicyRecord,
    A2ATaskRecord,
    AgentCardCacheEntry,
    TaskDirection,
)


class A2AGatewayRepository(Protocol):
    async def create_task(self, record: A2ATaskRecord) -> A2ATaskRecord: ...

    async def get_task(self, task_id: str) -> A2ATaskRecord | None: ...

    async def update_task_status(
        self, task_id: str, *, status: str, output_artifacts: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> A2ATaskRecord: ...

    async def list_tasks(
        self, *, tenant_id: str | None = None, direction: TaskDirection | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[A2ATaskRecord], int]: ...

    async def upsert_access_policy(self, record: A2AAccessPolicyRecord) -> A2AAccessPolicyRecord: ...

    async def get_access_policy(self, caller_agent_id: str, tenant_id: str) -> A2AAccessPolicyRecord | None: ...

    async def get_cached_card(self, agent_url: str) -> AgentCardCacheEntry | None: ...

    async def upsert_cached_card(self, entry: AgentCardCacheEntry) -> AgentCardCacheEntry: ...


class A2APeerClient(Protocol):
    async def fetch_agent_card(self, agent_url: str) -> dict[str, Any]:
        """GET `{agent_url}/.well-known/agent.json` on the target — the
        A2A spec's own discovery well-known path."""
        ...

    async def send_message(self, agent_url: str, *, skill_id: str, input_message: dict[str, Any]) -> dict[str, Any]:
        """POST a `message/send` JSON-RPC request to the target's own A2A
        endpoint. Returns the JSON-RPC `result` object on success; raises
        `A2APeerRpcError` if the target itself returned a JSON-RPC error."""
        ...


class WorkflowEngineClient(Protocol):
    async def start_instance(
        self, *, definition_id: str, tenant_id: str, initial_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Starts a Workflow Engine (Module 1) instance for an
        inbound-accepted task. Returns Workflow Engine's own
        `StartInstanceResponse` shape (`id`/`status`/`trace_id`)."""
        ...
