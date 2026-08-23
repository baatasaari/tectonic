"""In-memory fakes for the ports in core/ports.py — the unit-test tier,
mirroring the other modules' core/fakes.py.
"""
from __future__ import annotations

import copy
from typing import Any

from tool_orchestration.core.domain import (
    CircuitBreakerStateRecord,
    CircuitState,
    ReliabilityScoreRecord,
    ToolCallError,
    ToolDefinitionRecord,
    ToolInvocationRecord,
)


class InMemoryToolRepository:
    def __init__(self) -> None:
        self.tools: dict[str, ToolDefinitionRecord] = {}
        self.invocations: list[ToolInvocationRecord] = []
        self.reliability_scores: dict[str, ReliabilityScoreRecord] = {}

    def seed_tool(self, tool: ToolDefinitionRecord) -> None:
        self.tools[tool.id] = tool

    async def create_tool_definition(self, record: ToolDefinitionRecord) -> ToolDefinitionRecord:
        self.tools[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_tool_definition(self, tool_id: str) -> ToolDefinitionRecord | None:
        rec = self.tools.get(tool_id)
        return copy.deepcopy(rec) if rec else None

    async def update_tool_definition(self, record: ToolDefinitionRecord) -> ToolDefinitionRecord:
        self.tools[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def list_tool_definitions(self, tenant_id: str, status: str | None = None) -> list[ToolDefinitionRecord]:
        return [
            copy.deepcopy(t)
            for t in self.tools.values()
            if t.tenant_id == tenant_id and (status is None or t.status.value == status)
        ]

    async def create_tool_invocation(self, record: ToolInvocationRecord) -> ToolInvocationRecord:
        self.invocations.append(copy.deepcopy(record))
        return copy.deepcopy(record)

    async def get_reliability_score(self, tool_id: str) -> ReliabilityScoreRecord | None:
        rec = self.reliability_scores.get(tool_id)
        return copy.deepcopy(rec) if rec else None

    async def upsert_reliability_score(self, record: ReliabilityScoreRecord) -> ReliabilityScoreRecord:
        self.reliability_scores[record.tool_id] = copy.deepcopy(record)
        return copy.deepcopy(record)


class InMemoryCircuitBreakerStore:
    def __init__(self) -> None:
        self._states: dict[str, CircuitBreakerStateRecord] = {}

    async def get_state(self, tool_id: str) -> CircuitBreakerStateRecord:
        return copy.deepcopy(self._states.get(tool_id)) or CircuitBreakerStateRecord(tool_id=tool_id, state=CircuitState.CLOSED)

    async def set_state(self, record: CircuitBreakerStateRecord) -> None:
        self._states[record.tool_id] = copy.deepcopy(record)


class FakeMCPClientAdapter:
    """Simulates a set of MCP tool servers, each independently configurable
    to fail or succeed, for exercising retry/circuit-breaker deterministically."""

    def __init__(self) -> None:
        self.failing_tools: set[str] = set()
        self.calls: list[dict[str, Any]] = []

    async def call(self, *, mcp_server_ref: str, tool_name: str, arguments: dict[str, Any], tenant_id: str) -> dict[str, Any]:
        self.calls.append({"mcp_server_ref": mcp_server_ref, "tool_name": tool_name, "arguments": arguments})
        if tool_name in self.failing_tools:
            raise ToolCallError(tool_name, "simulated tool failure")
        return {"result": f"{tool_name}-ok", "arguments": arguments}


class StubLLMGatewayClient:
    async def complete(self, *, prompt_context: dict[str, Any], tenant_id: str) -> dict[str, Any]:
        return {
            "name": "synthesised_lookup_tool",
            "mcp_server_ref": "internal-synthesis",
            "schema": {"input": {"query": "string"}, "output": {"result": "string"}},
        }


class StubGuardrailsClient:
    def __init__(self) -> None:
        self.block_next = False

    async def check(self, *, content: dict[str, Any], policy_profile: str, tenant_id: str) -> tuple[bool, dict[str, Any]]:
        if self.block_next:
            return False, {"violation_category": "unsafe_tool_composition"}
        return True, {"policy_profile": policy_profile, "violations": []}


class StubSentinelAgentsClient:
    def __init__(self) -> None:
        self.submissions: list[dict[str, Any]] = []

    async def submit_for_review(self, *, tool_id: str, proposed_schema: dict[str, Any], tenant_id: str) -> str:
        self.submissions.append({"tool_id": tool_id, "proposed_schema": proposed_schema, "tenant_id": tenant_id})
        return f"sentinel-review-{tool_id}"
