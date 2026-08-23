"""Configuration schema for the Sentinel Agents module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseliningConfig(BaseModel):
    method: Literal["statistical", "isolation_forest"] = "statistical"
    sensitivity: Literal["low", "medium", "high"] = "medium"  # hot-reloadable


class SwarmDetectionConfig(BaseModel):
    enabled: bool = True
    correlation_window_seconds: int = Field(300, gt=0)
    min_agents: int = Field(3, ge=2)


class AutonomyLevelConfig(BaseModel):
    low_severity: Literal["alert_only", "autonomous_intervention"] = "alert_only"
    medium_severity: Literal["alert_only", "autonomous_intervention"] = "alert_only"
    high_severity: Literal["alert_only", "autonomous_intervention"] = "autonomous_intervention"


class InterventionConfig(BaseModel):
    autonomy_level: AutonomyLevelConfig = AutonomyLevelConfig()
    swarm_anomalies_always_escalate: bool = True  # cannot be overridden to autonomous, by design


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class SentinelAgentsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SENTINEL_AGENTS_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    baselining: BaseliningConfig = BaseliningConfig()
    swarm_detection: SwarmDetectionConfig = SwarmDetectionConfig()
    intervention: InterventionConfig = InterventionConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://sentinel_agents:sentinel_agents@localhost:5432/sentinel_agents"
    service_name: str = "sentinel-agents"
    http_port: int = 8094
    dependency_stub_base_url: str = "http://localhost:9115"


_HOT_RELOADABLE = {"baselining.sensitivity"}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> SentinelAgentsSettings:
    yaml_path = os.environ.get("SENTINEL_AGENTS_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("sentinel_agents", raw)
    return SentinelAgentsSettings(**overrides)
