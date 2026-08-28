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
    # A real default, the same "give a real local component a real localhost default"
    # convention every other module's own database_url/peer base_url fields already
    # follow -- NOT `None` silently meaning in-memory (independent architecture
    # assessment §10 "Vector DB": "in-memory Qdrant is the default", its highest-
    # severity finding for this module). `embedded_in_memory` below is the one,
    # explicit, unmissable way to opt into the in-memory client instead; `url` alone
    # can never silently produce it.
    url: str = "http://localhost:6333"
    # Explicit opt-in only -- main.py logs a loud startup warning whenever this is
    # true, the same posture jwt_shared_secret's own insecure-default warning takes.
    # True is correct for local dev and the unit-test tier (this module's own test
    # harness constructs its in-memory client directly and never reads this field --
    # see tests/conftest.py); it must never be true for a real deployment, since every
    # point indexed is lost on the next restart.
    embedded_in_memory: bool = False
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

    # Migration bookkeeping only (core/domain.py's MigrationRecord) -- Qdrant itself
    # remains the real vector data plane; this is what makes the *tracking* of an
    # in-flight re-embedding migration survive a restart (independent architecture
    # assessment §10: "migration state is in memory" was its own separate finding).
    # Low-traffic by nature (migrations are rare, operator-triggered events), so a
    # smaller pool than this platform's request-serving modules use.
    database_url: str = "postgresql+asyncpg://vector_db:vector_db@localhost:5432/vector_db"
    db_pool_size: int = 5
    db_max_overflow: int = 2
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts

    service_name: str = "vector-db"
    multi_tenancy_base_url: str = "http://localhost:8109"
    entitlement_gate_cache_ttl_seconds: float = 30.0
    http_port: int = 8089
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
