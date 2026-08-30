"""Configuration schema for the Deployment Strategy module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class DeploymentStrategySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEPLOYMENT_STRATEGY_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://deployment_strategy:deployment_strategy@localhost:5432/deployment_strategy"

    # Pool sized against this module's own Helm chart (deploy/helm/deployment-strategy/values.yaml):
    # maxReplicas=10 (operator/CI-driven rollout traffic, not per-request serving volume --
    # the same lighter ceiling LLMOps' own chart already uses), targeting
    # <=100 steady-state / <=150 burst connections platform-wide at full autoscale,
    # this platform's standard sizing formula.
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "deployment-strategy"
    multi_tenancy_base_url: str = "http://localhost:8109"
    entitlement_gate_cache_ttl_seconds: float = 30.0
    http_port: int = 8106

    # Canary Health Calculator thresholds (core/canary_health_calculator.py):
    # a composite score renormalized over whichever real signal(s) actually have data.
    min_groundedness_sample_size: int = 10
    min_health_score: float = 0.8
    groundedness_weight: float = 0.6
    cost_weight: float = 0.4
    budget_period: str = "monthly"

    evaluation_framework_base_url: str = "http://localhost:8097"
    finops_base_url: str = "http://localhost:8105"
    dependency_stub_base_url: str = "http://localhost:9127"

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


def load_settings() -> DeploymentStrategySettings:
    yaml_path = os.environ.get("DEPLOYMENT_STRATEGY_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("deployment-strategy", raw)
    return DeploymentStrategySettings(**overrides)
