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

    # Pool sized against this module's own Helm chart (deploy/helm/sentinel-agents/values.yaml):
    # maxReplicas=20, targeting <=100 steady-state / <=150 burst connections to
    # this module's own Postgres instance platform-wide at full autoscale.
    db_pool_size: int = 5
    db_max_overflow: int = 2
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "sentinel-agents"
    multi_tenancy_base_url: str = "http://localhost:8109"
    entitlement_gate_cache_ttl_seconds: float = 30.0
    http_port: int = 8094
    workflow_engine_base_url: str = "http://localhost:8080"
    tool_orchestration_base_url: str = "http://localhost:8083"
    human_oversight_base_url: str = "http://localhost:8095"
    auditability_base_url: str = "http://localhost:8099"

    # Service-to-service JWT auth (security/jwt_auth.py) — one shared secret across
    # every module, so this field's env var name is NOT prefixed like the rest of this
    # settings class: every module's Helm chart injects the same Kubernetes Secret under
    # this same literal env var name. The default is an insecure, obviously-a-placeholder
    # value so local dev/tests work with zero config; main.py logs a startup warning if
    # it's still active.
    jwt_shared_secret: str = Field(
        default="dev-insecure-shared-secret-change-me", validation_alias="TECTONIC_JWT_SHARED_SECRET",
    )
    jwt_ttl_seconds: int = 300


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
