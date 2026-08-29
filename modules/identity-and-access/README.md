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
    ports.py                    Repository, the real Auditability client port, OidcTokenVerifier
    fakes.py                     In-memory implementations of every port, for unit tests
    identity_registry_service.py  Identity Registry — register/revoke/reinstate
    role_service.py                Role Service — create/get/list
    token_service.py                Token Service — issues requested ∩ granted scoped tokens (role_names ∪ federated_role_names)
    authorization_service.py        Authorization Service — the zero-trust live authorize check
    identity_provider_service.py    Identity Provider Service — per-tenant OIDC/SAML config CRUD
    oidc_federation_service.py       OIDC Federation Service — verify + JIT-provision/update on login
    group_service.py                 Group Service — IdP-group -> default-role mapping, live recompute
    scim_token_service.py            SCIM Token Service — show-once per-tenant provisioning bearer tokens
    scim_service.py                   SCIM 2.0 User/Group lifecycle, mapped onto IdentityRecord/GroupRecord
  db/                      SQLAlchemy 2.0 async models + repository (Identity/Role/AuthDecision/IdentityProvider/Group/ScimToken)
  clients/                 Resilient HTTP client to Auditability
  security/
    jwt_auth.py               Service-to-service JWT (platform-wide shared secret, this module's own inbound protection); excludes /scim/* by prefix
    openapi_security.py       Real OpenAPI security scheme declaration (ServiceBearerAuth + ScimBearerAuth)
    token_signer.py             This module's own distinct signing key for the scoped tokens it issues
    oidc_verifier.py             Real JWKS-fetching, PyJWT-based OIDC ID token verifier
    scim_auth.py                  SCIM's own per-tenant bearer token dependency
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/
    routes_identity_and_access.py  FastAPI router — roles, identities, tokens, authorize, identity-providers, oidc/login, groups, scim-tokens
    routes_scim.py                   SCIM 2.0 router — /scim/v2/{tenant_id}/Users and /Groups
  schemas/
    identity_and_access.py     Pydantic request/response models for this module's own REST shapes
    scim.py                      Real SCIM 2.0 wire shapes (RFC 7643/7644) — ListResponse, PatchOp, User, Group
```

## Design notes vs. the LLD

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
- **SAML: a real, storable config model, and an honest, undisguised
  gap.** `IdentityProviderRecord` stores `provider_type=saml`,
  `sso_url`, and `x509_certificate` as real fields an operator can
  register and read back — but this module has no SAML assertion
  consumer service (ACS) endpoint and performs no XML-DSig
  verification anywhere. `OidcFederationService.login` raises
  `FederationError` for a non-OIDC provider rather than silently
  no-op'ing or, worse, accepting an unverified assertion. A real SAML
  ACS is substantial, security-critical, separate work (canonical XML,
  signature-wrapping-attack defenses, `xmlsec`-grade tooling); shipping
  a partial or unsigned parser would be strictly worse than shipping
  none, the same "document real gaps, never fabricate insecure crypto"
  call this platform already made for envelope encryption and the
  service-JWT boundary.
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
