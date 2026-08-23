"""Retry Manager (LLD §2.2): applies per-tool retry policy — exponential
backoff, configurable per tool. A tool's `schema.retry_policy` overrides the
platform default from config, following the same tiered override principle
Module 1 establishes (platform default -> tenant -> definition -> step;
here, platform default -> tool).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from tool_orchestration.config import RetryConfig
from tool_orchestration.core.domain import ToolCallError, ToolDefinitionRecord
from tool_orchestration.core.ports import MCPClientAdapter
from tool_orchestration.telemetry.metrics import tool_retries_total


@dataclass
class RetryOutcome:
    output: dict | None
    error: str | None
    retry_count: int
    success: bool


class RetryManager:
    def __init__(
        self, mcp_client: MCPClientAdapter, config: RetryConfig, sleep_fn=asyncio.sleep, backoff_base_seconds: float = 0.05
    ) -> None:
        self.mcp_client = mcp_client
        self.config = config
        self._sleep = sleep_fn
        self._backoff_base_seconds = backoff_base_seconds

    def _policy(self, tool: ToolDefinitionRecord) -> tuple[int, str]:
        policy = tool.schema.get("retry_policy", {})
        max_retries = policy.get("max_retries", self.config.default_max_retries)
        backoff_strategy = policy.get("backoff_strategy", self.config.default_backoff_strategy)
        return max_retries, backoff_strategy

    def _backoff_delay(self, strategy: str, attempt: int) -> float:
        if strategy == "none":
            return 0.0
        if strategy == "fixed":
            return self._backoff_base_seconds
        return self._backoff_base_seconds * (2 ** (attempt - 1))

    async def call_with_retry(
        self, tool: ToolDefinitionRecord, arguments: dict, agent_ref: str, tenant_id: str
    ) -> RetryOutcome:
        max_retries, backoff_strategy = self._policy(tool)
        attempt = 0
        last_error: str | None = None

        while attempt <= max_retries:
            try:
                output = await self.mcp_client.call(
                    mcp_server_ref=tool.mcp_server_ref, tool_name=tool.name, arguments=arguments, tenant_id=tenant_id
                )
                return RetryOutcome(output=output, error=None, retry_count=attempt, success=True)
            except ToolCallError as e:
                last_error = str(e)
                if attempt >= max_retries:
                    break
                attempt += 1
                tool_retries_total.labels(tool_id=tool.id).inc()
                delay = self._backoff_delay(backoff_strategy, attempt)
                if delay:
                    await self._sleep(delay)

        return RetryOutcome(output=None, error=last_error, retry_count=attempt, success=False)
