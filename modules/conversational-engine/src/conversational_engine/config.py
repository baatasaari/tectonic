"""Configuration schema for the Conversational Engine module (LLD §Level 4
"Configuration"). Loaded from YAML (WORKFLOW_ENGINE-style env override), same
base -> tenant -> definition -> step resolution principle Module 1 sets as
the platform-wide convention.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SessionConfig(BaseModel):
    ttl_seconds: int = 1800  # hot-reloadable, Redis session expiry
    cross_channel_continuity: bool = True  # feature flag, requires Long-Term Memory


class PersonaConfig(BaseModel):
    default_persona_config_ref: str = "default"


class HandoffConfig(BaseModel):
    emotion_score_threshold: float = Field(0.75, ge=0.0, le=1.0)  # hot-reloadable
    repeated_refusal_threshold: int = 3


class StreamingConfig(BaseModel):
    protocol: Literal["sse", "websocket"] = "sse"


class WorkflowRoutingConfig(BaseModel):
    """Added for the Phase 2 support-agent slice (ticket #82). Default off:
    every pre-existing turn keeps calling LLM Gateway directly, unchanged.
    When enabled, handle_turn() creates/drives a real Workflow Engine
    instance instead — see session_manager.py's own
    _handle_turn_via_workflow_engine docstring."""

    enabled: bool = False
    definition_id: str = "support-agent-v1"


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"
    debug_content_logging: bool = False


class ConversationalEngineSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CONVERSATIONAL_ENGINE_", env_nested_delimiter="__", extra="forbid"
    )

    tenant_id: str = "default"
    session: SessionConfig = SessionConfig()
    persona: PersonaConfig = PersonaConfig()
    handoff: HandoffConfig = HandoffConfig()
    streaming: StreamingConfig = StreamingConfig()
    telemetry: TelemetryConfig = TelemetryConfig()
    workflow_routing: WorkflowRoutingConfig = WorkflowRoutingConfig()

    database_url: str = "postgresql+asyncpg://conversational_engine:conversational_engine@localhost:5432/conversational_engine"

    # Pool sized against this module's own Helm chart (deploy/helm/conversational-engine/values.yaml):
    # maxReplicas=20, targeting <=100 steady-state / <=150 burst connections to
    # this module's own Postgres instance platform-wide at full autoscale.
    db_pool_size: int = 5
    db_max_overflow: int = 2
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    redis_url: str = "redis://localhost:6379/0"
    service_name: str = "conversational-engine"
    multi_tenancy_base_url: str = "http://localhost:8109"
    entitlement_gate_cache_ttl_seconds: float = 30.0
    # Bounded-staleness fallback window (security/entitlement_gate.py) -- how long a
    # VERIFIED entitlement decision may still be served after Multi-tenancy becomes
    # unreachable before the gate switches to fail-closed. Must exceed
    # entitlement_gate_cache_ttl_seconds to have any effect.
    entitlement_gate_max_staleness_seconds: float = 300.0
    http_port: int = 8081
    llm_gateway_base_url: str = "http://localhost:8082"
    # One shared virtual key for every completion this module makes -- see
    # clients/http_clients.py's own module docstring for why (the same
    # documented per-tenant-resolution deferral Workflow Engine's own
    # identical field already established, ticket #82).
    llm_gateway_virtual_key: str = "conversational-engine-default"
    # Added for the Phase 2 support-agent slice (ticket #82).
    workflow_engine_base_url: str = "http://localhost:8080"
    guardrails_base_url: str = "http://localhost:8093"
    long_term_memory_base_url: str = "http://localhost:8092"
    human_oversight_base_url: str = "http://localhost:8095"
    observability_base_url: str = "http://localhost:8098"
    auditability_base_url: str = "http://localhost:8099"

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


_HOT_RELOADABLE = {
    "session.ttl_seconds",
    "handoff.emotion_score_threshold",
    "telemetry.log_level",
}


def is_hot_reloadable(path: str) -> bool:
    return path in _HOT_RELOADABLE


def load_settings() -> ConversationalEngineSettings:
    yaml_path = os.environ.get("CONVERSATIONAL_ENGINE_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("conversational_engine", raw)
    return ConversationalEngineSettings(**overrides)
