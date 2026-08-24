"""Configuration schema for the Vector DB module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class QueryConfig(BaseModel):
    default_top_k: int = Field(10, gt=0)
    hybrid_search_default: bool = True  # hot-reloadable


class IsolationConfig(BaseModel):
    tenancy_model: Literal["shared_collection_with_filter", "dedicated_collection"] = "shared_collection_with_filter"


class MigrationConfig(BaseModel):
    batch_size: int = Field(1000, gt=0)
    verification_sample_rate: float = Field(0.05, ge=0.0, le=1.0)


class QdrantConfig(BaseModel):
    url: str | None = None  # None => embedded in-memory Qdrant (unit-test tier)
    collection_alias: str = "vector_db_points"
    default_embedding_model: str = "text-embedding-3-small"


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class VectorDbSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VECTOR_DB_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    query: QueryConfig = QueryConfig()
    isolation: IsolationConfig = IsolationConfig()
    migration: MigrationConfig = MigrationConfig()
    qdrant: QdrantConfig = QdrantConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    service_name: str = "vector-db"
    http_port: int = 8089
    dependency_stub_base_url: str = "http://localhost:9110"

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


_HOT_RELOADABLE = {"query.hybrid_search_default"}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> VectorDbSettings:
    yaml_path = os.environ.get("VECTOR_DB_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("vector_db", raw)
    return VectorDbSettings(**overrides)
