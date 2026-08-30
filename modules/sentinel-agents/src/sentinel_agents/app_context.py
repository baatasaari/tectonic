"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sentinel_agents.config import SentinelAgentsSettings
from sentinel_agents.core.ports import (
    AuditabilityClient,
    HumanOversightClient,
    ToolOrchestrationClient,
    WorkflowEngineClient,
)
from sentinel_agents.core.swarm_correlation import SwarmWindowTracker


@dataclass
class AppContext:
    settings: SentinelAgentsSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    workflow_engine: WorkflowEngineClient
    tool_orchestration: ToolOrchestrationClient
    human_oversight: HumanOversightClient
    auditability: AuditabilityClient
    window_tracker: SwarmWindowTracker
