"""Configuration schema for the Observability module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RetentionConfig(BaseModel):
    traces_days: int = 30  # hot-reloadable, customer/compliance-driven
    metrics_days: int = 90
    logs_days: int = 30


class ReasoningNarrativeConfig(BaseModel):
    enabled: bool = True  # feature flag


class CostAttributionConfig(BaseModel):
    enabled: bool = True


class WorkflowShapesConfig(BaseModel):
    expected_spans: dict[str, list[str]] = {}  # workflow_type -> [expected span names], for trace-completeness


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class ObservabilitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OBSERVABILITY_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    retention: RetentionConfig = RetentionConfig()
    reasoning_narrative: ReasoningNarrativeConfig = ReasoningNarrativeConfig()
    cost_attribution: CostAttributionConfig = CostAttributionConfig()
    workflow_shapes: WorkflowShapesConfig = WorkflowShapesConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://observability:observability@localhost:5432/observability"

    # Pool sized against this module's own Helm chart (deploy/helm/observability/values.yaml):
    # maxReplicas=20, targeting <=100 steady-state / <=150 burst connections to
    # this module's own Postgres instance platform-wide at full autoscale.
    db_pool_size: int = 5
    db_max_overflow: int = 2
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "observability"
    http_port: int = 8098
    dependency_stub_base_url: str = "http://localhost:9119"

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


_HOT_RELOADABLE = {"retention.traces_days", "reasoning_narrative.enabled", "cost_attribution.enabled"}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> ObservabilitySettings:
    yaml_path = os.environ.get("OBSERVABILITY_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("observability", raw)
    return ObservabilitySettings(**overrides)
