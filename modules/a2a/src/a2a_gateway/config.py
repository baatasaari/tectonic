"""Configuration schema for the A2A module (LLD §Level 4 "Configuration")."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class A2AGatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="A2A_GATEWAY_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://a2a_gateway:a2a_gateway@localhost:5432/a2a_gateway"

    # Pool sized against this module's own Helm chart (deploy/helm/a2a/values.yaml):
    # maxReplicas=20, targeting <=100 steady-state / <=150 burst connections platform-wide
    # at full autoscale, this platform's standard sizing formula.
    db_pool_size: int = 5
    db_max_overflow: int = 2
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "a2a"
    http_port: int = 8101
    dependency_stub_base_url: str = "http://localhost:9122"

    # This platform's own published Agent Card (served at /.well-known/agent.json) and the
    # inbound skill -> Workflow Engine definition mapping in one place: a skill this platform
    # accepts inbound (a key here) is exactly a skill this platform advertises outbound --
    # see core/local_card.py.
    agent_name: str = "tectonic-platform-agent"
    agent_description: str = "Tectonic Agentic AI Platform's own A2A-addressable agent."
    self_base_url: str = "http://localhost:8101"
    skill_definition_map: dict[str, str] = Field(default_factory=dict)

    agent_card_cache_ttl_seconds: int = 3600
    workflow_engine_base_url: str = "http://localhost:8080"

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


def load_settings() -> A2AGatewaySettings:
    yaml_path = os.environ.get("A2A_GATEWAY_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("a2a_gateway", raw)
    return A2AGatewaySettings(**overrides)
