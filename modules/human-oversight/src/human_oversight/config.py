"""Configuration schema for the Human Oversight module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class NotificationConfig(BaseModel):
    channels: list[str] = ["slack"]  # email | slack | teams | webhook, tenant can enable multiple
    escalation_on_timeout: bool = True  # re-notify or escalate to a secondary channel/reviewer group


class QueueConfig(BaseModel):
    default_timeout_seconds: int = Field(86400, gt=0)  # hot-reloadable, overridable per request
    priority_levels: list[str] = ["low", "medium", "high", "critical"]


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class HumanOversightSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HUMAN_OVERSIGHT_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    notification: NotificationConfig = NotificationConfig()
    queue: QueueConfig = QueueConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://human_oversight:human_oversight@localhost:5432/human_oversight"
    service_name: str = "human-oversight"
    http_port: int = 8095
    dependency_stub_base_url: str = "http://localhost:9116"


_HOT_RELOADABLE = {"queue.default_timeout_seconds"}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> HumanOversightSettings:
    yaml_path = os.environ.get("HUMAN_OVERSIGHT_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("human_oversight", raw)
    return HumanOversightSettings(**overrides)
