# Identity and Access — Module 31

The platform's identity registry and zero-trust authorization layer:
every user, agent and service gets its own registered, individually-
revocable identity (never a shared service account), assigned one or
more roles that bundle real scopes, and can request a scoped token
narrowed to the intersection of what it asked for and what its roles
actually grant. `authorize` is the one gate any platform module can
call to turn a token plus a required scope into a real, live, auditable
allow/deny decision. Full design doc:
[`../../docs/module-31-identity-and-access.md`](../../docs/module-31-identity-and-access.md).

## Layout

```
src/identity_and_access/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                  Pydantic Settings — LLD config schema
  core/
    domain.py                 IdentityRecord/RoleRecord/AuthDecisionRecord, IdentityProviderRecord/GroupRecord/ScimTokenRecord, the identity lifecycle state machine
    ports.py                    Repository, the real Auditability client port, OidcTokenVerifier, SamlAssertionVerifier
    fakes.py                     In-memory implementations of every port, for unit tests
    identity_registry_service.py  Identity Registry — register/revoke/reinstate
    role_service.py                Role Service — create/get/list, tenant-scoped
    role_binding_service.py         Role Binding Service — grant/revoke a role on an existing identity, real audit trail
    token_service.py                Token Service — issues requested ∩ granted scoped tokens (role_names ∪ federated_role_names)
    authorization_service.py        Authorization Service — the zero-trust live authorize check
    identity_provider_service.py    Identity Provider Service — per-tenant OIDC/SAML config CRUD
    oidc_federation_service.py       OIDC Federation Service — verify + JIT-provision/update on login
    saml_federation_service.py       SAML Federation Service — verify + JIT-provision/update on login
    federation_common.py             JIT-provisioning logic shared between OIDC and SAML
    group_service.py                 Group Service — IdP-group -> default-role mapping, live recompute
    scim_token_service.py            SCIM Token Service — show-once per-tenant provisioning bearer tokens
    scim_service.py                   SCIM 2.0 User/Group lifecycle, mapped onto IdentityRecord/GroupRecord
  db/                      SQLAlchemy 2.0 async models + repository (Identity/Role/RoleBinding/AuthDecision/IdentityProvider/Group/ScimToken)
  clients/                 Resilient HTTP client to Auditability
  security/
    jwt_auth.py               Service-to-service JWT (platform-wide shared secret, this module's own inbound protection); excludes /scim/* by prefix
    openapi_security.py       Real OpenAPI security scheme declaration (ServiceBearerAuth + ScimBearerAuth)
    token_signer.py             This module's own distinct signing key for the scoped tokens it issues
    oidc_verifier.py             Real JWKS-fetching, PyJWT-based OIDC ID token verifier
    saml_verifier.py              Real signxml-based SAML assertion (XML-DSig) verifier
    scim_auth.py                  SCIM's own per-tenant bearer token dependency
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/
    routes_identity_and_access.py  FastAPI router — roles, identities, role bindings, tokens, authorize, identity-providers, oidc/login, saml/login, groups, scim-tokens
    routes_scim.py                   SCIM 2.0 router — /scim/v2/{tenant_id}/Users and /Groups
  schemas/
    identity_and_access.py     Pydantic request/response models for this module's own REST shapes
    scim.py                      Real SCIM 2.0 wire shapes (RFC 7643/7644) — ListResponse, PatchOp, User, Group
```

## Design notes vs. the LLD

- **IAM v2 foundation: tenant-scoped roles and a real role-binding
  lifecycle.** (Independent architecture assessment §31, P0: "no...
  user/group/membership lifecycle" -- picked from that same finding's
  own backlog after the entitlement-gate bounded-staleness fix.) Before
  this, `RoleRecord`'s `name` was this module's sole, platform-global
  primary key -- one tenant creating a role called `"admin"` meant no
  other tenant could ever create their own `"admin"` (the second
  tenant's `create_role` call failed outright against the first
  tenant's row), and there was no way to grant or revoke a single role
  on an already-registered identity at all -- `role_names` could only
  ever be set once, at `register()` time. Both fixed:
  - **Roles are now tenant-scoped.** `RoleRecord` gained `id`/`tenant_id`;
    the table's primary key moved from `name` to `id`, with a real
    unique constraint on `(tenant_id, name)` (Alembic `0003`, which
    backfills every pre-existing role as a platform-wide default --
    see below -- rather than guessing which one tenant it should
    belong to, preserving exactly the access every existing identity
    already had). `POST /v1/identity-access/roles` and `GET .../roles`
    resolve `tenant_id` the same way every other tenant-scoped route in
    this module already does (`resolve_tenant_id`: the `X-Tenant-Id`
    header, falling back to this deployment's own configured
    `tenant_id`) -- there's no separate "admin" identity or elevated
    caller; posting a role while authenticated as tenant A creates it
    for tenant A, full stop.
  - **A `PLATFORM_TENANT_ID` sentinel (`"__platform__"`), not `None`,
    marks a platform-wide default role** -- kept consistent with every
    other `tenant_id` column/field in this module's data model, none of
    which is nullable. `RoleService.get`/`TokenService.issue`/
    `IdentityRegistryService.register`'s role-existence check all
    resolve a role name the same way: the calling tenant's own role of
    that name if one exists, else the platform-wide default of that
    name, else not found -- a tenant's own role shadows a
    platform-wide one of the same name rather than colliding with it.
    `GET /roles?tenant_id=...` deliberately does **not** auto-merge in
    platform-wide roles (an exact filter, matching every other
    `list_*` route in this module) -- a caller wanting both calls it
    twice, once with its own `tenant_id` and once with
    `PLATFORM_TENANT_ID`, rather than this module inventing
    merge/pagination semantics nobody asked for.
  - **Role bindings: a real grant/revoke lifecycle with its own audit
    trail.** New `POST /identities/{id}/roles` (grant),
    `POST /identities/{id}/roles/{role_name}/revoke`, and
    `GET /identities/{id}/role-bindings` (`core/role_binding_service.py`).
    `IdentityRecord.role_names` stays the fast-path "currently
    effective roles" list every other service already reads; each
    grant/revoke additionally writes/updates a durable
    `RoleBindingRecord` row (`granted_by`, `granted_at`, `revoked_at`)
    -- one row per grant, revoked in place rather than a second row, the
    same "materialized view + event log" split this module already
    uses for `AuthDecisionRecord` vs. the live `authorize()` check.
    Granting an already-held role is idempotent (no duplicate binding
    row); revoking a role never granted raises a clean 404
    (`RoleNotGrantedError`), not a silent no-op.
  - **Deliberately not built here** (out of scope for this pass, same
    "reference pattern in one place first" convention as this
    platform's other multi-module rollouts): a `TenantMembership`
    entity distinct from `RoleBindingRecord`. Every `IdentityRecord`
    already belongs to exactly one `tenant_id` for its whole life (set
    once at `register()`/JIT-provisioning time, never reassigned) --
    given that, a role binding *is* this module's membership record
    (identity × role, tenant-scoped); a third, redundant entity would
    only restate `IdentityRecord.tenant_id`. Cross-tenant identity
    membership (one human identity belonging to more than one tenant)
    isn't modeled at all -- a contractor working across two client
    tenants registers as two separate identities today, one per
    tenant, the same way SCIM/OIDC/SAML JIT-provisioning already treat
    every login as scoped to one `(tenant_id, provider_id)` pair.
- **Zero-trust actually means something here.** `AuthorizationService.
  authorize` re-checks the issuing identity's *current* status against
  the live registry on every single call — a revoked identity's
  outstanding tokens stop authorizing on the very next request, not
  whenever they happen to expire.
- **Token issuance can only ever narrow, never grant.**
  `TokenService.issue` mints a token carrying exactly `requested ∩
  granted` — never more than the identity's roles actually hold, even
  if the caller asks for more.
- **Two distinct secrets for two distinct trust boundaries.** This
  module's own inbound API is still protected by the platform-wide
  `TECTONIC_JWT_SHARED_SECRET` every module shares; the fine-grained,
  per-identity tokens it issues are signed with this module's own
  dedicated `token_signing_secret`. Compromising one never compromises
  the other.
- **Unauthorized attempts are a real, queryable audit trail.** Every
  `authorize` call is persisted, and every denial is also emitted as a
  real event to Auditability (Module 20)'s own `POST
  /v1/auditability/events` — the same real-peer emission pattern this
  platform's earlier modules (Human Oversight, Sentinel Agents,
  Regulatory Compliance) already established. A down Auditability peer
  degrades only the audit emission, never the auth decision itself.

- **OIDC federation: verify, then JIT-provision or update, never
  fabricate.** (Independent architecture assessment §31: "no complete
  OIDC/SAML federation, SCIM, user/group/membership lifecycle... or
  universal enforcement", maturity 38/100, P0.) `POST
  /v1/identity-access/oidc/login` takes a tenant's registered
  `IdentityProviderRecord` and a raw ID token, verifies it for real
  (`security/oidc_verifier.py`: fetch the provider's JWKS over HTTPS,
  cache it, match `kid`, verify signature/issuer/audience via PyJWT —
  the `cryptography` package this needs for RS256 is a precedented
  platform dependency, already pinned by Secrets and Credential
  Management's envelope encryption), then looks the identity up by
  `(tenant_id, provider_id, sub)` — never by email, which real IdPs
  reuse and reassign — creating a new `IdentityRecord` on first login
  and refreshing `name`/`email` on every one after. The token's
  `groups_claim` (a per-provider-configurable claim name, since IdPs
  disagree on it) is resolved against this tenant's registered
  `GroupRecord`s into `federated_role_names` fresh on *every* login —
  a separate list from the identity's manually-assigned `role_names`,
  unioned by `TokenService.issue` when computing a token's granted
  scopes, so removing someone from an IdP group revokes what that
  group granted on their very next login, without this module ever
  polling the IdP, and without a hand-granted role ever depending on
  federation staying configured correctly.
- **SAML: a real assertion consumer (ACS), real XML-DSig verification.**
  `POST /v1/identity-access/saml/login` takes the real SAML 2.0
  HTTP-POST binding's `SAMLResponse` (base64-encoded XML) and verifies
  it for real (`security/saml_verifier.py`, via `signxml`): the XML
  digital signature is checked against the tenant's registered
  `x509_certificate`, constrained to the exact expected `Assertion`
  location (`signxml`'s own documented SAML best practice — the real
  defense against a basic signature-wrapping attack, an attacker
  appending a second, unsigned or differently-signed `Assertion`
  elsewhere in the document while leaving the genuinely-signed one in
  place); only the verified `signed_xml` element is ever read from
  afterward, never the raw untrusted input tree. `Conditions/
  @NotBefore`/`@NotOnOrAfter` and `AudienceRestriction` (checked
  against `client_id`, reused from OIDC's identical "who is this
  for" concept rather than adding a second field) are validated by
  hand once the signature itself is trusted — `signxml` verifies the
  *signature*, not SAML's own semantic constraints, same as PyJWT
  leaving `exp`/`aud` to the caller. `SamlFederationService.login`
  then JIT-provisions/updates the identity by `(tenant_id, provider_id,
  NameID)` and resolves `federated_role_names` from the assertion's
  group-bearing attribute — identical semantics to OIDC, sharing the
  exact same provisioning logic via `core/federation_common.py` rather
  than duplicating it. `OidcFederationService.login`/
  `SamlFederationService.login` each still raise `FederationError` for
  the other provider type, so a misconfigured login attempt is refused,
  never silently no-op'd or (worse) accepted unverified. Verified with
  a real RSA keypair, a real self-signed X.509 certificate, and a real
  XML-DSig-signed assertion built and signed with `signxml` itself
  (`tests/unit/test_saml_verifier.py`) — including a tampered-assertion
  case (digest mismatch caught) and a signature from an untrusted key
  (correctly rejected even though internally self-consistent) — plus
  full JIT-provisioning coverage (`tests/unit/test_saml_federation_service.py`)
  mirroring OIDC's own.
- **SCIM 2.0 (RFC 7643/7644): Users and Groups, real wire shapes, its
  own auth.** `api/routes_scim.py` mounts a spec-shaped provisioning
  API at `/scim/v2/{tenant_id}/Users` and `.../Groups` — real
  `schemas` arrays, `meta`, `ListResponse`, `PatchOp` operations
  (`schemas/scim.py`), not an ad hoc subset. A SCIM User *is* an
  `IdentityRecord` (`type=user`), correlated by `email` (SCIM's
  `userName`); a SCIM Group is a `GroupRecord` with
  `provider_id="scim"`. Two bounded, deliberate simplifications: `filter=`
  query parsing supports exactly `userName eq "value"` (the load-bearing
  dedup-before-create case every IdP actually sends); `PATCH` supports
  `replace` of `active`/`userName`/`displayName` on Users and
  `add`/`remove`/`replace` of `members` on Groups, and silently ignores
  any other op/path rather than rejecting the request — real IdPs
  routinely PATCH attributes (`meta`, `schemas`) this module has no
  reason to act on. SCIM group membership is the one place `GroupRecord`
  membership is actually written (OIDC federation never persists it,
  deriving `federated_role_names` fresh from each login's own claim
  instead) — a `PATCH .../Groups/{id}` add/remove call recomputes every
  affected identity's `federated_role_names` immediately, live, the same
  posture `AuthorizationService.authorize` already takes for revocation.
  `DELETE /Groups/{id}` clears membership but doesn't hard-delete the
  row (`IdentityAccessRepository` has no `delete_group` — a real, small,
  documented gap, not a silent one).
- **SCIM authenticates itself, deliberately not through
  `ServiceAuthMiddleware`.** An external IdP pushing SCIM calls never
  holds `TECTONIC_JWT_SHARED_SECRET` — that secret is this platform's
  own internal module-to-module trust boundary. `POST
  /v1/identity-access/scim-tokens` mints a per-tenant bearer token
  (`core/scim_token_service.py`) shown in cleartext exactly once, at
  creation, and stored only as its SHA-256 hash — the same show-once
  posture this platform takes for API keys.
  `security/scim_auth.py`'s `require_scim_token` FastAPI dependency
  verifies it independently, scoped to the `{tenant_id}` path parameter
  (a token minted for one tenant is rejected outright against another's
  SCIM endpoint — not silently reinterpreted). `jwt_auth.py`'s
  `_EXCLUDED_PATH_PREFIXES` carves `/scim/*` out of
  `ServiceAuthMiddleware`'s enforcement by prefix (matched before
  FastAPI's own routing resolves `{tenant_id}`, so this can't be a
  route-parameter-aware exact match the way `/healthz`/`/metrics` are)
  — a different case from those two: SCIM paths are authenticated,
  just not by this mechanism, so `security/openapi_security.py`
  declares a second scheme (`ScimBearerAuth`) and marks every SCIM
  operation with it rather than the empty `security: []`
  `_EXCLUDED_PATHS` gets.

- **Its generated OpenAPI document declares the real auth it enforces**
  (`security/openapi_security.py`) — see Workflow Engine's README and the
  independent architecture assessment's §3.6 for the shared reference
  implementation and full reasoning. `ServiceAuthMiddleware` is plain
  Starlette middleware, invisible to FastAPI's automatic OpenAPI
  generation, so this module's spec previously declared no
  `securitySchemes` at all; `configure_openapi_security` fixes that,
  reusing `jwt_auth.py`'s own `_EXCLUDED_PATHS` as the one source of
  truth for which paths are genuinely unauthenticated.

- **Kubernetes hardening** (`deploy/helm/`; independent architecture
  assessment §3.7) — see Workflow Engine's README for the full reasoning
  and reference implementation. A dedicated ServiceAccount with no
  auto-mounted API token (this module never calls the Kubernetes API);
  pod/container `securityContext` (non-root, read-only root filesystem
  with a small `/tmp` `emptyDir`, all capabilities dropped, a seccomp
  profile); a `NetworkPolicy` restricting ingress to this module's own
  namespace; separate startup/liveness/readiness probe semantics instead
  of two identical probes; and `topologySpreadConstraints` across nodes.

- **NUL bytes/invalid enum values reaching the database or crashing
  unhandled** (ticket #82's platform-wide sweep, following the same bug
  a real CI run found on Multi-tenancy's and Billing and Metering's own
  contract tiers — see either module's own README for the original
  finding). `routes_identity_and_access.py`'s `GET /identities`,
  `/identity-providers`, `/groups` and `/scim-tokens` all took raw
  `tenant_id`/`provider_id` query parameters with no NUL-byte guard;
  fixed with `_reject_null_byte_query()`. `/identities`'s own `status`
  was a bare `str` hand-converted to `IdentityStatus`, raising an
  unhandled `ValueError` (500) for any non-member string (a NUL byte
  included) — now typed `IdentityStatus` directly so FastAPI/Pydantic
  itself rejects an invalid value with a clean 422.
  `routes_scim.py`'s SCIM `GET /Users`'s `filter` expression is
  regex-matched for an embedded `userName` value that then reaches the
  repository unguarded — same fix applied there.

- **Contract-test tier rolled out here** (P0 Phase 1A closure item;
  `tests/contract/`, `schemathesis`-driven fuzzing against a live ASGI
  app + real Postgres — reference implementation Multi-tenancy's own
  README documents, ticket #73/#80). Excludes `/scim/*` (a different
  auth mechanism this tier's own service-bearer token can't exercise
  meaningfully — see `tests/contract/conftest.py`'s own docstring).
  Its very first run found three real gaps, all previously invisible
  because this module had no contract tier until now:
  - `POST /roles` (and every other body field this pass covers)
    reached Postgres with a raw NUL byte and crashed with an unhandled
    500 instead of a clean 422 — the same `_reject_null_byte`
    field-validator pattern ticket #82's platform-wide sweep already
    established elsewhere, applied here for the first time to this
    module's own request schemas.
  - `RegisterIdentityRequest.type` and
    `RegisterIdentityProviderRequest.provider_type` were bare `str`
    fields hand-converted to `IdentityType`/`IdentityProviderType` at
    the route, raising an unhandled `ValueError`/500 for any
    non-member string — the identical sibling bug class ticket #82
    already fixed for `IdentityStatus` on the query-param side, never
    caught here on these two body fields. Now typed directly on the
    request schema so FastAPI/Pydantic itself rejects an invalid value
    with a clean 422.
  - `GET /identities/{id}`, `GET /identity-providers/{id}`, `GET
    /groups/{id}`, and `POST /scim-tokens/{id}/revoke` all handed a
    syntactically-invalid UUID path parameter straight to
    `session.get()`, crashing with an unhandled `DataError` instead of
    a clean 404 — this platform's own recurring "non-UUID path/
    query-param" bug class (first found in Multi-tenancy/Billing and
    Metering), fixed the same way: a `_is_valid_uuid` pre-check in
    `db/repository.py` that returns `None` (→ a typed NotFoundError →
    404) instead of ever reaching the database with a value that can't
    possibly name a real row.
  Every fix has its own regression test — the schema-level ones in
  `tests/unit/test_routes_identity_and_access.py` (provable with the
  in-memory fake, since Pydantic validation runs before either
  repository is ever reached), the UUID-format one in
  `tests/integration/test_repository_postgres.py` (real-Postgres-only:
  a dict lookup in the unit tier's own fake never crashes on a
  malformed key the way `asyncpg` does).

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest tests/unit                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```

## Testing tiers

| Tier | What it needs | How to run |
|---|---|---|
| Unit | Nothing — in-memory fakes only | `pytest tests/unit` |
| Integration (isolated) | Real Postgres (`TECTONIC_TEST_POSTGRES_URL` or Docker via `testcontainers`) | `pytest tests/integration` |
| Contract | Real Postgres (same as Integration) | `pytest tests/contract` |
