"""Configuration schema for the MCP module (LLD §Level 4 "Configuration")."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class MCPGatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCP_GATEWAY_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://mcp_gateway:mcp_gateway@localhost:5432/mcp_gateway"

    # Pool sized against this module's own Helm chart (deploy/helm/mcp/values.yaml):
    # maxReplicas=20, targeting <=100 steady-state / <=150 burst connections platform-wide
    # at full autoscale, this platform's standard sizing formula.
    db_pool_size: int = 5
    db_max_overflow: int = 2
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "mcp"
    http_port: int = 8100
    dependency_stub_base_url: str = "http://localhost:9121"

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


def load_settings() -> MCPGatewaySettings:
    yaml_path = os.environ.get("MCP_GATEWAY_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("mcp_gateway", raw)
    return MCPGatewaySettings(**overrides)
