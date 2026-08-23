"""Tool Orchestration Service (LLD §3.4, §3.5): the single point through
which every agent action against an external tool passes — checks the
circuit breaker, dispatches through the Retry Manager, updates the
Reliability Scorer and circuit breaker state from the outcome, and logs the
invocation. This module's central coordinator, same role as the other three
modules' orchestrators.
"""
from __future__ import annotations

import time

from tool_orchestration.core.circuit_breaker import CircuitBreaker
from tool_orchestration.core.domain import (
    CircuitOpenError,
    InvocationOutcome,
    InvocationStatus,
    ToolCallError,
    ToolInvocationRecord,
    ToolNotActiveError,
    ToolNotFoundError,
    ToolStatus,
    new_id,
)
from tool_orchestration.core.ports import CircuitBreakerStore, ToolRepository
from tool_orchestration.core.reliability_scorer import ReliabilityScorer
from tool_orchestration.core.retry_manager import RetryManager
from tool_orchestration.telemetry.logging import get_logger
from tool_orchestration.telemetry.metrics import (
    tool_dispatch_overhead_seconds,
    tool_invocation_duration_seconds,
    tool_invocations_total,
)

logger = get_logger(component="orchestration_service")


class ToolOrchestrationService:
    def __init__(
        self,
        repository: ToolRepository,
        circuit_breaker_store: CircuitBreakerStore,
        circuit_breaker: CircuitBreaker,
        retry_manager: RetryManager,
        reliability_scorer: ReliabilityScorer,
    ) -> None:
        self.repository = repository
        self.circuit_breaker_store = circuit_breaker_store
        self.circuit_breaker = circuit_breaker
        self.retry_manager = retry_manager
        self.reliability_scorer = reliability_scorer

    async def invoke(
        self, *, tool_id: str, arguments: dict, agent_ref: str, tenant_id: str, workflow_instance_id: str | None = None
    ) -> InvocationOutcome:
        overhead_start = time.perf_counter()

        tool = await self.repository.get_tool_definition(tool_id)
        if tool is None:
            raise ToolNotFoundError(tool_id)
        if tool.status != ToolStatus.ACTIVE:
            raise ToolNotActiveError(f"tool '{tool_id}' is not active (status={tool.status.value})")

        cb_state = await self.circuit_breaker_store.get_state(tool_id)
        allowed, cb_state = self.circuit_breaker.may_call(cb_state)
        if not allowed:
            await self.circuit_breaker_store.set_state(cb_state)
            tool_invocations_total.labels(tenant_id=tenant_id, tool_id=tool_id, outcome="circuit_open").inc()
            raise CircuitOpenError(tool_id, cb_state.next_retry_at)

        tool_dispatch_overhead_seconds.observe(time.perf_counter() - overhead_start)

        call_start = time.perf_counter()
        result = await self.retry_manager.call_with_retry(tool, arguments, agent_ref, tenant_id)
        latency_ms = (time.perf_counter() - call_start) * 1000
        tool_invocation_duration_seconds.labels(tool_id=tool_id).observe(latency_ms / 1000)

        current_score = await self.repository.get_reliability_score(tool_id)
        new_score = self.reliability_scorer.update(current_score, tool_id, result.success, latency_ms)
        await self.repository.upsert_reliability_score(new_score)

        cb_state = self.circuit_breaker.record_result(cb_state, new_score, result.success)
        await self.circuit_breaker_store.set_state(cb_state)

        status = InvocationStatus.COMPLETED if result.success else InvocationStatus.FAILED
        await self.repository.create_tool_invocation(
            ToolInvocationRecord(
                id=new_id(), tool_id=tool_id, agent_ref=agent_ref, workflow_instance_id=workflow_instance_id,
                status=status, retry_count=result.retry_count, latency_ms=latency_ms,
            )
        )
        tool_invocations_total.labels(tenant_id=tenant_id, tool_id=tool_id, outcome=status.value).inc()

        if not result.success:
            raise ToolCallError(tool_id, result.error or "tool call failed")

        return InvocationOutcome(
            status=status, output=result.output, error=None, retry_count=result.retry_count, latency_ms=latency_ms
        )
