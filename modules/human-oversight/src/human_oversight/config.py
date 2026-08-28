"""Configuration schema for the Human Oversight module (LLD §Level 4
"Configuration")."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# The platform's own well-known local-dev port convention (docs/openapi/README.md) --
# used as PLATFORM_SERVICE_URLS' default so HTTPDecisionCallbackDispatcher can resolve
# *any* requesting_module's real base URL, not just the one hardcoded elsewhere in this
# file. A real cluster deployment overrides this whole field via one JSON env var
# pointing at Kubernetes service DNS names instead (pydantic-settings parses a
# dict[str, str] field from a JSON-encoded env var natively).
_PLATFORM_SERVICE_PORTS: dict[str, int] = {
    "workflow-engine": 8080, "conversational-engine": 8081, "llm-gateway": 8082,
    "tool-orchestration": 8083, "intent-detection": 8084, "agentic-rag": 8085,
    "context-engineering": 8086, "data-source-plugins": 8087, "knowledge-base": 8088,
    "vector-db": 8089, "graph-db": 8090, "short-term-memory": 8091, "long-term-memory": 8092,
    "guardrails": 8093, "sentinel-agents": 8094, "human-oversight": 8095,
    "regulatory-compliance": 8096, "evaluation-framework": 8097, "observability": 8098,
    "auditability": 8099, "mcp": 8100, "a2a": 8101, "agent-cards": 8102,
    "agent-marketplace": 8103, "llmops": 8104, "finops": 8105, "deployment-strategy": 8106,
    "multi-modality": 8107, "promptops": 8108, "multi-tenancy": 8109, "identity-and-access": 8110,
    "secrets-and-credential-management": 8111, "billing-and-metering": 8112,
    "sdk-and-developer-portal": 8113,
}


def _default_service_urls() -> dict[str, str]:
    return {name: f"http://localhost:{port}" for name, port in _PLATFORM_SERVICE_PORTS.items()}


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

    # Pool sized against this module's own Helm chart (deploy/helm/human-oversight/values.yaml):
    # maxReplicas=10, targeting <=100 steady-state / <=150 burst connections to
    # this module's own Postgres instance platform-wide at full autoscale.
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # avoid stale connections behind cloud LB/proxy idle timeouts
    service_name: str = "human-oversight"
    http_port: int = 8095
    auditability_base_url: str = "http://localhost:8099"

    # HTTPDecisionCallbackDispatcher's real service directory: `notify()` calls back to
    # whichever module raised the original oversight request, a target that varies per
    # call, so (unlike every other peer client in this module) it can't be bound to one
    # fixed base_url at construction. Resolved per call by requesting_module.
    service_urls: dict[str, str] = Field(default_factory=_default_service_urls)

    # Slack/Teams/generic-webhook are tenant-configured external integrations, not
    # Tectonic peer modules -- they have no fixed port in the platform's own service
    # directory above. A single shared stub URL is a reasonable placeholder for local
    # dev/test (the dependency-stub simulates all three at distinct paths); a real
    # deployment needs per-tenant webhook URLs (from tenant config, not a platform-wide
    # default), which is real, unbuilt work this field deliberately does not claim to do.
    notification_stub_base_url: str = "http://localhost:9095"

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
