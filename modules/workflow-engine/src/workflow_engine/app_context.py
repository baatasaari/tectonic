"""Process-wide wiring: everything that lives for the life of the app and is
shared across requests (DB engine, event publisher, dependency-module
clients, the symbolic rule registry). Built once in main.py's lifespan and
stashed on `app.state.ctx`; request-scoped objects (DB session, repository,
scheduler) are constructed per-request in api/deps.py from this.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from workflow_engine.config import WorkflowEngineSettings
from workflow_engine.core.ports import (
    GuardrailsClient,
    HumanOversightClient,
    LLMGatewayClient,
    ToolOrchestrationClient,
)
from workflow_engine.core.symbolic import SymbolicRuleExecutor


@dataclass
class AppContext:
    settings: WorkflowEngineSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    event_publisher: object  # EventPublisher protocol
    llm_gateway: LLMGatewayClient
    tool_orchestration: ToolOrchestrationClient
    guardrails: GuardrailsClient
    human_oversight: HumanOversightClient
    symbolic_executor: SymbolicRuleExecutor
