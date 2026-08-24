"""In-memory fakes for the ports in core/ports.py — the unit-test tier,
mirroring Modules 1 and 2's core/fakes.py.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

from llm_gateway.core.domain import (
    BudgetPolicyRecord,
    ChatMessage,
    CompletionResult,
    ProviderConfigRecord,
    ProviderError,
    RequestLogRecord,
    VirtualKeyRecord,
)


class InMemoryGatewayRepository:
    def __init__(self) -> None:
        self.virtual_keys: dict[str, VirtualKeyRecord] = {}
        self.budget_policies: dict[str, BudgetPolicyRecord] = {}
        self.request_logs: list[RequestLogRecord] = []
        self.provider_configs: dict[str, ProviderConfigRecord] = {}

    async def create_virtual_key(self, record: VirtualKeyRecord) -> VirtualKeyRecord:
        self.virtual_keys[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def get_virtual_key(self, virtual_key_id: str) -> VirtualKeyRecord | None:
        rec = self.virtual_keys.get(virtual_key_id)
        return copy.deepcopy(rec) if rec else None

    async def list_virtual_keys(
        self, tenant_id: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[VirtualKeyRecord], int]:
        matching = [v for v in self.virtual_keys.values() if v.tenant_id == tenant_id]
        matching.sort(key=lambda v: v.created_at, reverse=True)
        sliced = [copy.deepcopy(v) for v in matching[offset : offset + limit]]
        return sliced, len(matching)

    async def get_budget_policy(self, budget_policy_id: str) -> BudgetPolicyRecord | None:
        rec = self.budget_policies.get(budget_policy_id)
        return copy.deepcopy(rec) if rec else None

    async def create_budget_policy(self, record: BudgetPolicyRecord) -> BudgetPolicyRecord:
        self.budget_policies[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    async def update_budget_spend(self, budget_policy_id: str, new_spend: float) -> BudgetPolicyRecord:
        rec = self.budget_policies[budget_policy_id]
        rec = replace(rec, current_spend=new_spend)
        self.budget_policies[budget_policy_id] = rec
        return copy.deepcopy(rec)

    async def create_request_log(self, record: RequestLogRecord) -> RequestLogRecord:
        self.request_logs.append(copy.deepcopy(record))
        return copy.deepcopy(record)

    async def list_provider_configs(self) -> list[ProviderConfigRecord]:
        return [copy.deepcopy(p) for p in self.provider_configs.values()]

    async def update_provider_config(self, record: ProviderConfigRecord) -> ProviderConfigRecord:
        self.provider_configs[record.id] = copy.deepcopy(record)
        return copy.deepcopy(record)

    def seed_provider(self, provider: ProviderConfigRecord) -> None:
        self.provider_configs[provider.id] = provider


class FakeQualityScoreProvider:
    def __init__(self, default: float = 0.5, scores: dict[tuple[str, str, str], float] | None = None) -> None:
        self.default = default
        self.scores = scores or {}

    async def get_score(self, provider: str, model: str, task_type: str) -> float:
        return self.scores.get((provider, model, task_type), self.default)


class FakeProviderClient:
    """Simulates a set of providers, each independently configurable to
    fail or succeed, for exercising the Failover Manager deterministically."""

    def __init__(self) -> None:
        self.failing_providers: set[str] = set()
        self.cost_per_call: float = 0.002
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self, *, provider: str, model: str, messages: list[ChatMessage], tenant_id: str
    ) -> CompletionResult:
        self.calls.append({"provider": provider, "model": model, "tenant_id": tenant_id})
        if provider in self.failing_providers:
            raise ProviderError(provider, "simulated provider failure")
        input_tokens = sum(len(m.content.split()) for m in messages)
        return CompletionResult(
            content=f"[{provider}/{model}] response",
            input_tokens=input_tokens,
            output_tokens=8,
            cost=self.cost_per_call,
            model_used=model,
        )

    async def embed(self, *, provider: str, model: str, text: str, tenant_id: str) -> list[float]:
        if provider in self.failing_providers:
            raise ProviderError(provider, "simulated provider failure")
        return [float(len(text))] * 8
