"""Process-wide wiring, mirroring Module 1's app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from conversational_engine.config import ConversationalEngineSettings
from conversational_engine.core.ports import (
    AuditabilityClient,
    GuardrailsClient,
    HumanOversightClient,
    LLMGatewayClient,
    LongTermMemoryClient,
    ObservabilityClient,
    WorkflowEngineClient,
)


@dataclass
class AppContext:
    settings: ConversationalEngineSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    llm_gateway: LLMGatewayClient
    guardrails: GuardrailsClient
    long_term_memory: LongTermMemoryClient
    human_oversight: HumanOversightClient
    observability: ObservabilityClient
    auditability: AuditabilityClient
    workflow_engine: WorkflowEngineClient | None = None
