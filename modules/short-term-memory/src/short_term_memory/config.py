"""Configuration schema for the Short-Term Memory module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BufferConfig(BaseModel):
    default_token_budget: int = Field(4000, gt=0)  # hot-reloadable
    session_ttl_seconds: int = Field(1800, gt=0)


class SalienceConfig(BaseModel):
    scoring_method: Literal["rule_based", "llm_based"] = "rule_based"
    retention_priority_threshold: float = Field(0.7, ge=0.0, le=1.0)  # items above this retained verbatim


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class ShortTermMemorySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SHORT_TERM_MEMORY_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    buffer: BufferConfig = BufferConfig()
    salience: SalienceConfig = SalienceConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    redis_url: str = "redis://localhost:6379/0"
    service_name: str = "short-term-memory"
    multi_tenancy_base_url: str = "http://localhost:8109"
    entitlement_gate_cache_ttl_seconds: float = 30.0
    http_port: int = 8091
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


_HOT_RELOADABLE = {"buffer.default_token_budget"}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> ShortTermMemorySettings:
    yaml_path = os.environ.get("SHORT_TERM_MEMORY_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("short_term_memory", raw)
    return ShortTermMemorySettings(**overrides)
