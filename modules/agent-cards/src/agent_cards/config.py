"""Configuration schema for the Agent Cards module (LLD §Level 4 "Configuration")."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelemetryConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


class AgentCardsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_CARDS_", env_nested_delimiter="__", extra="forbid")

    tenant_id: str = "default"
    telemetry: TelemetryConfig = TelemetryConfig()

    database_url: str = "postgresql+asyncpg://agent_cards:agent_cards@localhost:5432/agent_cards"

    # Pool sized against this module's own Helm chart (deploy/helm/agent-cards/values.yaml):
    # maxReplicas=20, targeting <=100 steady-state / <=150 burst connections platform-wide
    # at full autoscale, this platform's standard sizing formula.
    db_pool_size: int = 5
    db_max_overflow: int = 2
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "agent-cards"
    http_port: int = 8102

    # Trust score weights -- config, not hardcoded, so a deployment that only cares about
    # one signal can zero out the other's weight without a code change. Renormalized over
    # whichever signal(s) actually have data at computation time (core/trust_score_calculator.py).
    performance_weight: float = 0.6
    compliance_weight: float = 0.4
    compliance_framework_name: str = "eu_ai_act"
    card_staleness_ttl_seconds: int = 86400

    evaluation_framework_base_url: str = "http://localhost:8097"
    regulatory_compliance_base_url: str = "http://localhost:8096"
    dependency_stub_base_url: str = "http://localhost:9123"

    # Entitlement gate (security/entitlement_gate.py) -- this module is the platform's
    # reference implementation of the per-module feature-flag check (see the rollout
    # playbook doc). Multi-tenancy is the system of record; the cache TTL bounds how
    # stale an entitlement change can appear here versus the added load on Multi-tenancy.
    multi_tenancy_base_url: str = "http://localhost:8109"
    entitlement_gate_cache_ttl_seconds: float = 30.0
    # Bounded-staleness fallback window (security/entitlement_gate.py) -- how long a
    # VERIFIED entitlement decision may still be served after Multi-tenancy becomes
    # unreachable before the gate switches to fail-closed. Must exceed
    # entitlement_gate_cache_ttl_seconds to have any effect.
    entitlement_gate_max_staleness_seconds: float = 300.0

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


def load_settings() -> AgentCardsSettings:
    yaml_path = os.environ.get("AGENT_CARDS_CONFIG_FILE")
    overrides: dict = {}
    if yaml_path and Path(yaml_path).is_file():
        with open(yaml_path) as f:
            raw = yaml.safe_load(f) or {}
        overrides = raw.get("agent_cards", raw)
    return AgentCardsSettings(**overrides)
