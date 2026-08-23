"""Failover Manager (LLD §2.2, §3.4): retries against an alternate provider
on failure. Wraps the ProviderClient port (LiteLLM in production) with a
platform-specific retry policy on top of whatever failover LiteLLM itself
provides.
"""
from __future__ import annotations

from dataclasses import dataclass

from llm_gateway.core.domain import (
    AllProvidersExhaustedError,
    ChatMessage,
    CompletionResult,
    ProviderError,
)
from llm_gateway.core.ports import ProviderClient
from llm_gateway.telemetry.logging import get_logger
from llm_gateway.telemetry.metrics import llm_gateway_failover_total

logger = get_logger(component="failover_manager")


@dataclass
class FailoverOutcome:
    result: CompletionResult
    provider_used: str
    attempts: int


class FailoverManager:
    def __init__(self, provider_client: ProviderClient, max_attempts: int) -> None:
        self.provider_client = provider_client
        self.max_attempts = max_attempts

    async def call_with_failover(
        self, candidates: list[str], *, model: str, messages: list[ChatMessage], tenant_id: str
    ) -> FailoverOutcome:
        if not candidates:
            raise AllProvidersExhaustedError("no eligible provider candidates")

        last_error: Exception | None = None
        previous_provider: str | None = None
        for attempt, provider in enumerate(candidates[: self.max_attempts], start=1):
            try:
                result = await self.provider_client.complete(
                    provider=provider, model=model, messages=messages, tenant_id=tenant_id
                )
                if previous_provider is not None:
                    llm_gateway_failover_total.labels(from_provider=previous_provider, to_provider=provider).inc()
                return FailoverOutcome(result=result, provider_used=provider, attempts=attempt)
            except ProviderError as e:
                logger.warning("provider_call_failed", provider=provider, attempt=attempt, error=str(e))
                last_error = e
                previous_provider = provider
                continue

        raise AllProvidersExhaustedError(
            f"all {min(len(candidates), self.max_attempts)} provider attempts failed"
        ) from last_error
