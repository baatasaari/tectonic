"""Admin-scoped request/response models (LLD §3.3)."""
from __future__ import annotations

from pydantic import BaseModel, field_validator


def _reject_null_byte(value: str) -> str:
    """Postgres's `text`/`varchar`/`json` columns are UTF-8 and reject the
    NUL byte outright (`asyncpg.exceptions.UntranslatableCharacterError`)
    -- a value `str` is happy to hold but the database is not. Schema-
    valid per OpenAPI (`type: string` says nothing about NUL), so
    nothing upstream of the DB call rejects it without this: caught
    here as a clean `422` instead of the request reaching the database
    at all (found by this module's own OpenAPI contract-test tier --
    the same fix Multi-tenancy's and Billing and Metering's own
    `_reject_null_byte` already established; ticket #82's platform-wide
    sweep). This module wasn't in that sweep's original module list --
    this specific gap was found by actually running the contract tier
    once the sweep's Query()-parameter pass was otherwise done."""
    if "\x00" in value:
        raise ValueError("must not contain a NUL byte (unsupported by Postgres's text encoding)")
    return value


class CreateVirtualKeyRequest(BaseModel):
    tenant_id: str
    provider_scope: list[str] = []
    budget_policy_ref: str

    @field_validator("tenant_id", "budget_policy_ref")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)

    @field_validator("provider_scope")
    @classmethod
    def _validate_provider_scope(cls, value: list[str]) -> list[str]:
        for item in value:
            _reject_null_byte(item)
        return value


class VirtualKeyResponse(BaseModel):
    id: str
    tenant_id: str
    provider_scope: list[str]
    budget_policy_ref: str
    status: str


class VirtualKeyListResponse(BaseModel):
    items: list[VirtualKeyResponse]
    total: int
    limit: int
    offset: int


class BudgetStatusResponse(BaseModel):
    id: str
    tenant_id: str
    period: str
    limit_amount: float
    current_spend: float
    utilisation_ratio: float
    alert_threshold_pct: float
    alert: bool


class ProviderStatusResponse(BaseModel):
    provider_name: str
    priority: int
    health_status: str
    deprecation_notices: list[dict]


class CreateProviderConfigRequest(BaseModel):
    """Ticket #82 (Phase 2 support-agent slice): before this, this module had
    no way at all -- through its own real API -- to provision a provider a
    tenant's completions could actually route to; `list_provider_configs`/
    `update_provider_config` both assumed a row already existed via some
    other, never-built mechanism (not even a data migration seeded one)."""

    provider_name: str
    endpoint: str
    priority: int = 0

    @field_validator("provider_name", "endpoint")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)


class CreateBudgetPolicyRequest(BaseModel):
    tenant_id: str
    period: str
    limit_amount: float
    alert_threshold_pct: float = 0.8

    @field_validator("tenant_id")
    @classmethod
    def _validate_no_null_byte(cls, value: str) -> str:
        return _reject_null_byte(value)


class BudgetPolicyResponse(BaseModel):
    id: str
    tenant_id: str
    period: str
    limit_amount: float
    current_spend: float
    alert_threshold_pct: float
