"""Configuration schema for the Knowledge Base module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChunkingConfig(BaseModel):
    default_strategy: Literal["fixed_size", "semantic", "structural"] = "semantic"
    default_chunk_size_tokens: int = Field(512, gt=0)
    overlap_tokens: int = Field(50, ge=0)


class StalenessConfig(BaseModel):
    default_threshold_days: int = Field(180, gt=0)  # hot-reloadable, overridable per document
    auto_flag_enabled: bool = True


class PolicyConfig(BaseModel):
    default_inheritance: Literal["document_level"] = "document_level"  # chunk-level tags override this default


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class KnowledgeBaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KNOWLEDGE_BASE_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    chunking: ChunkingConfig = ChunkingConfig()
    staleness: StalenessConfig = StalenessConfig()
    policy: PolicyConfig = PolicyConfig()
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://knowledge_base:knowledge_base@localhost:5432/knowledge_base"

    # Pool sized against this module's own Helm chart (deploy/helm/knowledge-base/values.yaml):
    # maxReplicas=20, targeting <=100 steady-state / <=150 burst connections to
    # this module's own Postgres instance platform-wide at full autoscale.
    db_pool_size: int = 5
    db_max_overflow: int = 2
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "knowledge-base"
    http_port: int = 8088
    vector_db_base_url: str = "http://localhost:8089"
    graph_db_base_url: str = "http://localhost:8090"

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


_HOT_RELOADABLE = {"staleness.default_threshold_days"}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> KnowledgeBaseSettings:
    yaml_path = os.environ.get("KNOWLEDGE_BASE_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("knowledge_base", raw)
    return KnowledgeBaseSettings(**overrides)
