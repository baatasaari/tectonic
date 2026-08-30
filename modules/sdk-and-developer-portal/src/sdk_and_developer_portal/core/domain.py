"""Framework-agnostic domain objects (LLD §3 data model)."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


def spec_hash(spec_json: dict[str, Any]) -> str:
    """A deterministic content hash of an OpenAPI spec -- the same
    input always hashes the same, which is what makes SDK regeneration
    idempotent: an unchanged spec never produces SDK churn."""
    canonical = json.dumps(spec_json, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class DeveloperStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


# The developer lifecycle state machine: one-way, the same shape Secrets and Credential
# Management (Module 32) and Billing and Metering (Module 33) both already established
# for their own terminal transitions.
_LEGAL_TRANSITIONS: dict[DeveloperStatus, set[DeveloperStatus]] = {
    DeveloperStatus.ACTIVE: {DeveloperStatus.REVOKED},
    DeveloperStatus.REVOKED: set(),
}


def is_legal_transition(from_status: DeveloperStatus, to_status: DeveloperStatus) -> bool:
    return to_status in _LEGAL_TRANSITIONS.get(from_status, set())


class DeveloperNotFoundError(Exception):
    def __init__(self, developer_id: str) -> None:
        super().__init__(f"Developer account not found: {developer_id}")


class DeveloperRevokedError(Exception):
    def __init__(self, developer_id: str) -> None:
        super().__init__(f"Developer account is revoked: {developer_id}")


class InvalidTransitionError(Exception):
    def __init__(self, from_status: DeveloperStatus, to_status: DeveloperStatus) -> None:
        super().__init__(f"Illegal transition: {from_status.value} -> {to_status.value}")
        self.from_status = from_status
        self.to_status = to_status


class ModuleCatalogEntryNotFoundError(Exception):
    def __init__(self, module_name: str) -> None:
        super().__init__(f"Module catalog entry not found: {module_name}")


class SdkPackageNotFoundError(Exception):
    def __init__(self, package_id: str) -> None:
        super().__init__(f"SDK package not found: {package_id}")


class UnsupportedSdkLanguageError(Exception):
    def __init__(self, language: str) -> None:
        super().__init__(f"Unsupported SDK language: {language!r} (supported: {sorted(SUPPORTED_SDK_LANGUAGES)})")


SUPPORTED_SDK_LANGUAGES = frozenset({"python"})


@dataclass
class DeveloperAccountRecord:
    id: str
    name: str
    email: str
    tenant_id: str
    identity_id: str
    status: DeveloperStatus = DeveloperStatus.ACTIVE
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)


@dataclass
class ModuleCatalogEntryRecord:
    module_name: str
    base_url: str
    title: str
    version: str
    path_count: int
    spec_json: dict[str, Any]
    spec_hash: str
    last_synced_at: datetime = field(default_factory=now)


@dataclass
class SdkPackageRecord:
    id: str
    module_name: str
    language: str
    version: int
    source_code: str
    spec_hash: str
    generated_at: datetime = field(default_factory=now)


@dataclass
class AdoptionMetrics:
    """What `AdoptionMetricsService.time_to_first_call` returns --
    both fields `None` when the developer's sandbox has no recorded
    activity yet. Insufficient data over a fabricated zero."""

    first_call_at: datetime | None
    time_to_first_call_seconds: float | None


@dataclass
class AdoptionRateReport:
    adopted_count: int
    total_developers: int
    rate: float | None
