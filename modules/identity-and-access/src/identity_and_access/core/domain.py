"""Framework-agnostic domain objects (LLD §3 data model)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class IdentityType(StrEnum):
    USER = "user"
    AGENT = "agent"
    SERVICE = "service"


class IdentityStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class IdentityProviderType(StrEnum):
    OIDC = "oidc"
    SAML = "saml"


# The identity lifecycle state machine (LLD §Level 3 "The identity lifecycle state
# machine"): any transition not a value here is illegal and raises
# InvalidTransitionError -- the same shape this platform's other state machines
# (Agent Marketplace, LLMOps, Deployment Strategy, PromptOps, Multi-tenancy) already
# established.
_LEGAL_TRANSITIONS: dict[IdentityStatus, set[IdentityStatus]] = {
    IdentityStatus.ACTIVE: {IdentityStatus.REVOKED},
    IdentityStatus.REVOKED: {IdentityStatus.ACTIVE},
}


def is_legal_transition(from_status: IdentityStatus, to_status: IdentityStatus) -> bool:
    return to_status in _LEGAL_TRANSITIONS.get(from_status, set())


class IdentityNotFoundError(Exception):
    def __init__(self, identity_id: str) -> None:
        super().__init__(f"Identity not found: {identity_id}")


class IdentityNotActiveError(Exception):
    def __init__(self, identity_id: str) -> None:
        super().__init__(f"Identity is not active: {identity_id}")


class RoleNotFoundError(Exception):
    def __init__(self, role_name: str) -> None:
        super().__init__(f"Role not found: {role_name}")


class InvalidTransitionError(Exception):
    def __init__(self, from_status: IdentityStatus, to_status: IdentityStatus) -> None:
        super().__init__(f"Illegal transition: {from_status.value} -> {to_status.value}")
        self.from_status = from_status
        self.to_status = to_status


class IdentityProviderNotFoundError(Exception):
    def __init__(self, provider_id: str) -> None:
        super().__init__(f"Identity provider not found: {provider_id}")


class GroupNotFoundError(Exception):
    def __init__(self, group_id: str) -> None:
        super().__init__(f"Group not found: {group_id}")


class FederationError(Exception):
    """A federated login failed for a reason that is genuinely the
    caller's fault -- not this module's -- e.g. an unknown/disabled
    provider, a token that fails signature/issuer/audience verification,
    or one missing the configured email/subject claim."""


class ScimTokenInvalidError(Exception):
    def __init__(self) -> None:
        super().__init__("SCIM bearer token is missing, unknown, or revoked")


class ScimConflictError(Exception):
    """A SCIM write collided with an existing resource (e.g. `userName`
    already provisioned for this tenant) -- maps to SCIM's own 409."""


@dataclass
class RoleRecord:
    name: str
    scopes: list[str] = field(default_factory=list)
    description: str = ""
    created_at: datetime = field(default_factory=now)


@dataclass
class IdentityRecord:
    id: str
    tenant_id: str
    name: str
    type: IdentityType = IdentityType.AGENT
    status: IdentityStatus = IdentityStatus.ACTIVE
    role_names: list[str] = field(default_factory=list)
    # Manually assigned, stable -- an operator sets these directly (register()/
    # a future role-grant endpoint) and they survive federated logins untouched.
    email: str | None = None
    # Set only for an identity JIT-provisioned by OidcFederationService; both are
    # None for an identity registered directly via IdentityRegistryService.register().
    external_provider_id: str | None = None
    external_subject: str | None = None
    # Federation-managed, volatile -- recomputed from scratch on every federated
    # login from the IdP's *current* group membership (OidcFederationService),
    # never hand-edited. Kept as a separate list from role_names, not merged into
    # it, so a manually-granted role is never silently dropped just because an
    # IdP-side group happened to change; TokenService.issue unions both when
    # computing the scopes a token can carry.
    federated_role_names: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)


@dataclass
class IdentityProviderRecord:
    """Per-tenant external IdP configuration. SAML support is deliberately
    config-model-only here -- `sso_url`/`x509_certificate` are stored and
    returned by the CRUD endpoints, but this module does not parse or
    verify a SAML assertion's XML-DSig signature anywhere (see
    core/oidc_federation_service.py's module docstring and this module's
    README for the honest reasoning: a real SAML assertion consumer is
    real, non-trivial cryptographic work, and shipping an unsigned or
    partially-verified parser would be worse than not shipping one)."""

    id: str
    tenant_id: str
    name: str
    provider_type: IdentityProviderType
    issuer: str
    enabled: bool = True
    # OIDC fields
    client_id: str = ""
    jwks_uri: str = ""
    # SAML fields (config-model only -- see the docstring above)
    sso_url: str = ""
    x509_certificate: str = ""
    # Claim/attribute names this provider uses for the fields OidcFederationService
    # needs -- IdPs disagree on these (Okta vs. Azure AD vs. Google Workspace), so
    # they're per-provider config, not a hardcoded guess.
    email_claim: str = "email"
    groups_claim: str = "groups"
    name_claim: str = "name"
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)


@dataclass
class GroupRecord:
    """An IdP group, mapped to the roles a member should hold while that
    group membership is current. Looked up by (tenant_id, provider_id,
    external_id) -- the IdP's own group identifier/name from the `groups`
    (or provider-configured `groups_claim`) claim -- not by this record's
    own `id`, which is purely this module's internal primary key."""

    id: str
    tenant_id: str
    provider_id: str
    external_id: str
    name: str
    default_role_names: list[str] = field(default_factory=list)
    # Identity IDs currently in this group. Populated two ways: OIDC federation
    # never writes this (OidcFederationService derives federated_role_names fresh
    # from each login's own groups claim and never persists membership); SCIM
    # group PATCH/PUT (core/scim_service.py) is the one real writer, since SCIM's
    # own contract is push-based membership with no analogous "login" event to
    # recompute from -- membership has to be durable. A flat list rather than a
    # join table, the same "flexible field over new table" call this platform
    # already makes for Multi-tenancy's ResourceAllocation.resources; fine at the
    # group sizes SCIM-managed IdP groups run at, not built for scale.
    member_identity_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=now)


@dataclass
class ScimTokenRecord:
    """A per-tenant SCIM provisioning bearer token. `token_hash` is a
    SHA-256 hex digest -- the cleartext token is minted once
    (ScimTokenService.create), returned to the caller exactly that one
    time, and never stored or reconstructible afterward, the same
    show-once posture this platform typically takes for API keys."""

    id: str
    tenant_id: str
    name: str
    token_hash: str
    created_at: datetime = field(default_factory=now)
    revoked: bool = False


@dataclass
class AuthDecisionRecord:
    id: str
    tenant_id: str
    identity_id: str
    required_scope: str
    allowed: bool
    reason: str
    checked_at: datetime = field(default_factory=now)


@dataclass
class IssuedToken:
    token: str
    granted_scopes: list[str]


@dataclass
class AuthDecisionResult:
    allowed: bool
    reason: str
