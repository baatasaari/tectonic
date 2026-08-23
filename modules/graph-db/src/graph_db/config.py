"""Configuration schema for the Graph DB module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class QueryConfig(BaseModel):
    default_max_traversal_depth: int = Field(3, gt=0)  # hot-reloadable, guards against runaway queries
    raw_cypher_enabled: bool = False  # feature flag, default off — see README "Design notes vs. the LLD"


class TemporalConfig(BaseModel):
    default_as_of: str = "now"


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class GraphDbSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GRAPH_DB_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    query: QueryConfig = QueryConfig()
    temporal: TemporalConfig = TemporalConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://graph_db:graph_db@localhost:5432/graph_db"
    service_name: str = "graph-db"
    http_port: int = 8090
    dependency_stub_base_url: str = "http://localhost:9111"


_HOT_RELOADABLE = {"query.default_max_traversal_depth"}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> GraphDbSettings:
    yaml_path = os.environ.get("GRAPH_DB_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("graph_db", raw)
    return GraphDbSettings(**overrides)
