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
    service_name: str = "intent-detection"
    http_port: int = 8084
    dependency_stub_base_url: str = "http://localhost:9105"


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
