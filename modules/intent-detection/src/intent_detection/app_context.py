"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from intent_detection.config import IntentDetectionSettings
from intent_detection.core.compositional_decomposer import CompositionalDecomposer
from intent_detection.core.drift_monitor import DriftMonitor
from intent_detection.core.ports import LLMGatewayClient
from intent_detection.core.primary_classifier import PrimaryClassifier


@dataclass
class AppContext:
    settings: IntentDetectionSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    llm_gateway: LLMGatewayClient
    primary_classifier: PrimaryClassifier
    decomposer: CompositionalDecomposer
    drift_monitor: DriftMonitor
