"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tool_orchestration.clients.mcp_http_client import HTTPMCPClientAdapter
from tool_orchestration.config import ToolOrchestrationSettings
from tool_orchestration.core.ports import GuardrailsClient, LLMGatewayClient, SentinelAgentsClient


@dataclass
class AppContext:
    settings: ToolOrchestrationSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    mcp_client: HTTPMCPClientAdapter
    llm_gateway: LLMGatewayClient
    guardrails: GuardrailsClient
    sentinel: SentinelAgentsClient
