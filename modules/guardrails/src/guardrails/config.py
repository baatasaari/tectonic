"""Configuration schema for the Guardrails module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChecksConfig(BaseModel):
    pii_detection_enabled: bool = True
    jailbreak_detection_enabled: bool = True
    groundedness_check_enabled: bool = True
    denied_topics: list[str] = []  # tenant-specific, additive to platform defaults


class PiiConfig(BaseModel):
    entity_types: list[str] = ["EMAIL", "PHONE_NUMBER", "PERSON", "CREDIT_CARD"]
    action: Literal["redact", "block"] = "redact"


class GroundednessConfig(BaseModel):
    threshold: float = Field(0.85, ge=0.0, le=1.0)  # hot-reloadable


class RedTeamConfig(BaseModel):
    schedule: Literal["hourly", "daily", "weekly"] = "daily"
    enabled: bool = True  # feature flag, strongly recommended not to disable
    attempts_per_run: int = Field(10, gt=0)


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class GuardrailsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GUARDRAILS_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    checks: ChecksConfig = ChecksConfig()
    pii: PiiConfig = PiiConfig()
    groundedness: GroundednessConfig = GroundednessConfig()
    red_team: RedTeamConfig = RedTeamConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://guardrails:guardrails@localhost:5432/guardrails"

    # Pool sized against this module's own Helm chart (deploy/helm/guardrails/values.yaml):
    # maxReplicas=30, targeting <=100 steady-state / <=150 burst connections to
    # this module's own Postgres instance platform-wide at full autoscale.
    db_pool_size: int = 4
    db_max_overflow: int = 2
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "guardrails"
    http_port: int = 8093
    dependency_stub_base_url: str = "http://localhost:9114"


_HOT_RELOADABLE = {"groundedness.threshold"}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> GuardrailsSettings:
    yaml_path = os.environ.get("GUARDRAILS_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("guardrails", raw)
    return GuardrailsSettings(**overrides)
