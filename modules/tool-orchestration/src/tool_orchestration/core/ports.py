"""Abstract ports the orchestration engine depends on: persistence, circuit
breaker state, the MCP protocol adapter, and the tool synthesis
dependencies (LLM Gateway, Guardrails, Sentinel Agents). Same testability
contract as the other modules.
"""
from __future__ import annotations

from typing import Any, Protocol

from tool_orchestration.core.domain import (
    CircuitBreakerStateRecord,
    ReliabilityScoreRecord,
    ToolDefinitionRecord,
    ToolInvocationRecord,
)


class ToolRepository(Protocol):
    async def create_tool_definition(self, record: ToolDefinitionRecord) -> ToolDefinitionRecord: ...

    async def get_tool_definition(self, tool_id: str) -> ToolDefinitionRecord | None: ...

    async def update_tool_definition(self, record: ToolDefinitionRecord) -> ToolDefinitionRecord: ...

    async def list_tool_definitions(
        self, tenant_id: str, status: str | None = None, *, limit: int = 50, offset: int = 0,
    ) -> tuple[list[ToolDefinitionRecord], int]: ...

    async def create_tool_invocation(self, record: ToolInvocationRecord) -> ToolInvocationRecord: ...

    async def get_reliability_score(self, tool_id: str) -> ReliabilityScoreRecord | None: ...

    async def upsert_reliability_score(self, record: ReliabilityScoreRecord) -> ReliabilityScoreRecord: ...


class CircuitBreakerStore(Protocol):
    """Redis-backed in production — fast read/write, natural TTL for the
    half-open retry window."""

    async def get_state(self, tool_id: str) -> CircuitBreakerStateRecord: ...

    async def set_state(self, record: CircuitBreakerStateRecord) -> None: ...


class MCPClientAdapter(Protocol):
    """Handles the actual MCP protocol calls to registered tool servers."""

    async def call(
        self, *, mcp_server_ref: str, tool_name: str, arguments: dict[str, Any], tenant_id: str
    ) -> dict[str, Any]: ...


class LLMGatewayClient(Protocol):
    async def complete(
        self, *, prompt_context: dict[str, Any], tenant_id: str
    ) -> dict[str, Any]: ...


class GuardrailsClient(Protocol):
    async def check(
        self, *, content: dict[str, Any], policy_profile: str, tenant_id: str
    ) -> tuple[bool, dict[str, Any]]: ...


class SentinelAgentsClient(Protocol):
    async def submit_for_review(
        self, *, tool_id: str, proposed_schema: dict[str, Any], tenant_id: str
    ) -> str:
        """Returns a review ticket/ref id — the actual approve/reject
        decision comes back later via the module's own
        `/tools/{id}/approve` endpoint, not synchronously here."""
        ...
