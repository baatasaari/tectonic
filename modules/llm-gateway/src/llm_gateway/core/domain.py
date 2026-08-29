"""Framework-agnostic domain objects (LLD §3.1 data model)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class VirtualKeyStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class BudgetPeriod(StrEnum):
    DAILY = "daily"
    MONTHLY = "monthly"


class RequestOutcome(StrEnum):
    COMPLETED = "completed"
    CACHE_HIT = "cache_hit"
    BUDGET_REJECTED = "rejected"
    FAILED = "failed"


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class VirtualKeyRecord:
    id: str
    tenant_id: str
    provider_scope: list[str]  # empty = all providers allowed
    budget_policy_ref: str
    status: VirtualKeyStatus = VirtualKeyStatus.ACTIVE
    created_at: datetime = field(default_factory=now)


@dataclass
class BudgetPolicyRecord:
    id: str
    tenant_id: str
    period: BudgetPeriod
    limit_amount: float
    current_spend: float = 0.0
    alert_threshold_pct: float = 0.8


@dataclass
class RequestLogRecord:
    id: str
    tenant_id: str
    virtual_key_id: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    cache_hit: bool
    latency_ms: float
    created_at: datetime = field(default_factory=now)


@dataclass
class ProviderConfigRecord:
    id: str
    provider_name: str
    endpoint: str
    priority: int
    health_status: str = "healthy"  # healthy|degraded|down
    deprecation_notices: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CompletionRequest:
    model: str
    messages: list[ChatMessage]
    tenant_id: str
    virtual_key_id: str
    routing_hints: dict[str, Any] = field(default_factory=dict)
    task_type: str = "chat"


@dataclass
class CompletionResult:
    """What a provider call produced — the ProviderClient port's return type."""

    content: str
    input_tokens: int
    output_tokens: int
    cost: float
    model_used: str


@dataclass
class CompletionResponse:
    content: str
    provider_used: str
    model_used: str
    cache_hit: bool
    cost: float
    input_tokens: int
    output_tokens: int
    latency_ms: float


class ProviderError(Exception):
    def __init__(self, provider: str, message: str):
        self.provider = provider
        super().__init__(f"{provider}: {message}")


class BudgetExceededError(Exception):
    pass


class AllProvidersExhaustedError(Exception):
    pass


class VirtualKeyInvalidError(Exception):
    pass


class QuotaExceededError(Exception):
    """Raised when Multi-tenancy's real `requests_per_minute` quota check
    denies this request (independent architecture assessment §5.2 /
    §3.4 point 5) -- a genuine, tenant-configured rate limit, not this
    module's own budget policy (`BudgetExceededError` is a separate,
    pre-existing concept: cost governance, not request-rate quota).
    Maps to a real `429 Too Many Requests`."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
