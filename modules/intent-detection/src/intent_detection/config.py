"""Configuration schema for the Intent Detection module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ClassificationConfig(BaseModel):
    confidence_threshold: float = Field(0.7, ge=0.0, le=1.0)  # hot-reloadable, below triggers fallback
    multi_intent_detection_enabled: bool = True


class DriftMonitoringConfig(BaseModel):
    enabled: bool = True
    check_frequency: Literal["hourly", "daily", "weekly"] = "daily"
    alert_threshold: float = 0.15


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class IntentDetectionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INTENT_DETECTION_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    classification: ClassificationConfig = ClassificationConfig()
    drift_monitoring: DriftMonitoringConfig = DriftMonitoringConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://intent_detection:intent_detection@localhost:5432/intent_detection"

    # Pool sized against this module's own Helm chart (deploy/helm/intent-detection/values.yaml):
    # maxReplicas=20, targeting <=100 steady-state / <=150 burst connections to
    # this module's own Postgres instance platform-wide at full autoscale.
    db_pool_size: int = 5
    db_max_overflow: int = 2
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "intent-detection"
    multi_tenancy_base_url: str = "http://localhost:8109"
    entitlement_gate_cache_ttl_seconds: float = 30.0
    http_port: int = 8084
    llm_gateway_base_url: str = "http://localhost:8082"

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


_HOT_RELOADABLE = {"classification.confidence_threshold"}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> IntentDetectionSettings:
    yaml_path = os.environ.get("INTENT_DETECTION_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("intent_detection", raw)
    return IntentDetectionSettings(**overrides)
