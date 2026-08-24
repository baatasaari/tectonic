"""Abstract ports the gateway's core logic depends on: persistence, cache,
quality-score feed, embeddings, and the provider adapter layer (LiteLLM in
production). Same testability contract as Modules 1 and 2.
"""
from __future__ import annotations

from typing import Protocol

from llm_gateway.core.domain import (
    BudgetPolicyRecord,
    ChatMessage,
    CompletionResult,
    ProviderConfigRecord,
    RequestLogRecord,
    VirtualKeyRecord,
)


class GatewayRepository(Protocol):
    async def create_virtual_key(self, record: VirtualKeyRecord) -> VirtualKeyRecord: ...

    async def get_virtual_key(self, virtual_key_id: str) -> VirtualKeyRecord | None: ...

    async def list_virtual_keys(
        self, tenant_id: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[VirtualKeyRecord], int]: ...

    async def get_budget_policy(self, budget_policy_id: str) -> BudgetPolicyRecord | None: ...

    async def create_budget_policy(self, record: BudgetPolicyRecord) -> BudgetPolicyRecord: ...

    async def update_budget_spend(self, budget_policy_id: str, new_spend: float) -> BudgetPolicyRecord: ...

    async def create_request_log(self, record: RequestLogRecord) -> RequestLogRecord: ...

    async def list_provider_configs(self) -> list[ProviderConfigRecord]: ...

    async def update_provider_config(self, record: ProviderConfigRecord) -> ProviderConfigRecord: ...


class SemanticCache(Protocol):
    async def lookup(self, model: str, messages: list[ChatMessage], tenant_id: str) -> CompletionResult | None: ...

    async def store(
        self, model: str, messages: list[ChatMessage], tenant_id: str, result: CompletionResult
    ) -> None: ...

    async def invalidate_stale(self, tenant_id: str) -> int:
        """Drop cache entries flagged stale by drift detection. Returns count invalidated."""
        ...


class QualityScoreProvider(Protocol):
    """Consumed from the Evaluation Framework via event bus in production,
    stored in Redis for sub-millisecond routing-time lookup per the LLD."""

    async def get_score(self, provider: str, model: str, task_type: str) -> float:
        """0..1, higher is better. Falls back to a neutral 0.5 when unknown."""
        ...


class SecretsClient(Protocol):
    """Port to the Secrets and Credential Management module. Provider API
    keys are never stored locally (LLD stack table) — fetched per call (or
    cached briefly by the adapter) from this port instead."""

    async def get_provider_api_key(self, provider: str, tenant_id: str) -> str: ...


class ProviderClient(Protocol):
    """The LiteLLM Provider Adapter Layer, behind a port — same pattern as
    Module 1 keeping ADK behind ExecutionScheduler: swapping in real LiteLLM
    means implementing this Protocol, without touching the router, cost
    governance, or failover logic that drives it."""

    async def complete(
        self, *, provider: str, model: str, messages: list[ChatMessage], tenant_id: str
    ) -> CompletionResult: ...

    async def embed(self, *, provider: str, model: str, text: str, tenant_id: str) -> list[float]: ...
