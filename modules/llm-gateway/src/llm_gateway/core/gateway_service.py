"""LLM Gateway Service (LLD §3.4): orchestrates cache lookup, quality-aware
routing, cost governance and provider failover for one completion request —
this module's central coordinator, same role as Module 1's Execution
Scheduler and Module 2's Session Manager.
"""
from __future__ import annotations

import time

from llm_gateway.config import LLMGatewaySettings
from llm_gateway.core.cost_governance import CostGovernanceEngine
from llm_gateway.core.domain import (
    AllProvidersExhaustedError,
    BudgetExceededError,
    CompletionRequest,
    CompletionResponse,
    QuotaExceededError,
    RequestLogRecord,
    VirtualKeyInvalidError,
    VirtualKeyStatus,
    new_id,
)
from llm_gateway.core.failover import FailoverManager
from llm_gateway.core.ports import GatewayRepository, MultiTenancyQuotaClient, SemanticCache
from llm_gateway.core.router import QualityAwareRouter
from llm_gateway.telemetry.logging import get_logger
from llm_gateway.telemetry.metrics import (
    llm_gateway_budget_utilisation_ratio,
    llm_gateway_cost_total,
    llm_gateway_overhead_seconds,
    llm_gateway_request_duration_seconds,
    llm_gateway_requests_total,
)

logger = get_logger(component="gateway_service")


class LLMGatewayService:
    def __init__(
        self,
        repository: GatewayRepository,
        cache: SemanticCache,
        router: QualityAwareRouter,
        cost_governance: CostGovernanceEngine,
        failover: FailoverManager,
        settings: LLMGatewaySettings,
        multi_tenancy: MultiTenancyQuotaClient | None = None,
    ) -> None:
        self.repository = repository
        self.cache = cache
        self.router = router
        self.cost_governance = cost_governance
        self.failover = failover
        self.settings = settings
        self.multi_tenancy = multi_tenancy

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        overhead_start = time.perf_counter()
        request_start = time.perf_counter()

        vk = await self.repository.get_virtual_key(request.virtual_key_id)
        if vk is None or vk.status != VirtualKeyStatus.ACTIVE:
            raise VirtualKeyInvalidError(f"virtual key '{request.virtual_key_id}' is not active")
        if vk.tenant_id != request.tenant_id:
            raise VirtualKeyInvalidError("virtual key does not belong to the requesting tenant")

        # Real pre-flight quota check (independent architecture assessment §5.2 /
        # §3.4 point 5) -- requests_per_minute, checked once per incoming request
        # (cache hit or not: a cache hit is still an accepted request from the
        # tenant's own quota perspective). tokens_per_minute isn't checked
        # pre-flight -- actual token count is unknown until the completion itself
        # runs, a genuinely different, real, separate accounting design; this
        # module's real, tested reference implementation is the rate-shaped check
        # that fits naturally as a pre-flight gate. `self.multi_tenancy` is
        # optional so this module's own unit tests that construct the service
        # directly without a Multi-tenancy client keep working unchanged.
        if self.multi_tenancy is not None:
            allowed, reason = await self.multi_tenancy.check_quota(
                tenant_id=request.tenant_id, resource_class="requests_per_minute",
            )
            if not allowed:
                llm_gateway_requests_total.labels(
                    tenant_id=request.tenant_id, provider="none", model=request.model, outcome="rejected"
                ).inc()
                raise QuotaExceededError(reason or "requests_per_minute quota exceeded")

        if self.settings.cache.semantic_cache_enabled:
            cached = await self.cache.lookup(request.model, request.messages, request.tenant_id)
            if cached is not None:
                latency_ms = (time.perf_counter() - request_start) * 1000
                await self._log(request, vk, provider="cache", model=cached.model_used, cache_hit=True, cost=0.0,
                                 input_tokens=cached.input_tokens, output_tokens=cached.output_tokens, latency_ms=latency_ms)
                llm_gateway_requests_total.labels(
                    tenant_id=request.tenant_id, provider="cache", model=cached.model_used, outcome="completed"
                ).inc()
                return CompletionResponse(
                    content=cached.content,
                    provider_used="cache",
                    model_used=cached.model_used,
                    cache_hit=True,
                    cost=0.0,
                    input_tokens=cached.input_tokens,
                    output_tokens=cached.output_tokens,
                    latency_ms=latency_ms,
                )

        providers = await self.repository.list_provider_configs()
        candidates = await self.router.rank_candidates(
            providers,
            model=request.model,
            task_type=request.task_type,
            allowed_provider_names=vk.provider_scope or None,
            priority_override=self.settings.failover.provider_priority_override,
        )

        try:
            await self.cost_governance.check_and_reserve_budget(vk.budget_policy_ref)
        except BudgetExceededError:
            llm_gateway_requests_total.labels(
                tenant_id=request.tenant_id, provider="none", model=request.model, outcome="rejected"
            ).inc()
            raise

        llm_gateway_overhead_seconds.observe(time.perf_counter() - overhead_start)

        try:
            outcome = await self.failover.call_with_failover(
                candidates, model=request.model, messages=request.messages, tenant_id=request.tenant_id
            )
        except AllProvidersExhaustedError:
            await self.cost_governance.settle(vk.budget_policy_ref, actual_cost=0.0)
            llm_gateway_requests_total.labels(
                tenant_id=request.tenant_id, provider="none", model=request.model, outcome="error"
            ).inc()
            raise

        policy = await self.cost_governance.settle(vk.budget_policy_ref, actual_cost=outcome.result.cost)
        llm_gateway_budget_utilisation_ratio.labels(
            tenant_id=request.tenant_id, budget_policy_id=policy.id
        ).set(self.cost_governance.utilisation_ratio(policy))

        if self.settings.cache.semantic_cache_enabled:
            await self.cache.store(request.model, request.messages, request.tenant_id, outcome.result)

        latency_ms = (time.perf_counter() - request_start) * 1000
        await self._log(
            request, vk, provider=outcome.provider_used, model=outcome.result.model_used, cache_hit=False,
            cost=outcome.result.cost, input_tokens=outcome.result.input_tokens, output_tokens=outcome.result.output_tokens,
            latency_ms=latency_ms,
        )
        llm_gateway_requests_total.labels(
            tenant_id=request.tenant_id, provider=outcome.provider_used, model=outcome.result.model_used, outcome="completed"
        ).inc()
        llm_gateway_cost_total.labels(
            tenant_id=request.tenant_id, provider=outcome.provider_used, model=outcome.result.model_used
        ).inc(outcome.result.cost)
        llm_gateway_request_duration_seconds.labels(
            provider=outcome.provider_used, model=outcome.result.model_used
        ).observe(latency_ms / 1000)

        return CompletionResponse(
            content=outcome.result.content,
            provider_used=outcome.provider_used,
            model_used=outcome.result.model_used,
            cache_hit=False,
            cost=outcome.result.cost,
            input_tokens=outcome.result.input_tokens,
            output_tokens=outcome.result.output_tokens,
            latency_ms=latency_ms,
        )

    async def _log(
        self, request: CompletionRequest, vk, *, provider: str, model: str, cache_hit: bool, cost: float,
        input_tokens: int, output_tokens: int, latency_ms: float,
    ) -> None:
        await self.repository.create_request_log(
            RequestLogRecord(
                id=new_id(),
                tenant_id=request.tenant_id,
                virtual_key_id=vk.id,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                cache_hit=cache_hit,
                latency_ms=latency_ms,
            )
        )
