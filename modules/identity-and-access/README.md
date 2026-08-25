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
    domain.py                 IdentityRecord/RoleRecord/AuthDecisionRecord, the identity lifecycle state machine
    ports.py                    Repository, the real Auditability client port
    fakes.py                     In-memory implementations of every port, for unit tests
    identity_registry_service.py  Identity Registry — register/revoke/reinstate
    role_service.py                Role Service — create/get/list
    token_service.py                Token Service — issues requested ∩ granted scoped tokens
    authorization_service.py        Authorization Service — the zero-trust live authorize check
  db/                      SQLAlchemy 2.0 async models + repository (Identity/Role/AuthDecision)
  clients/                 Resilient HTTP client to Auditability
  security/
    jwt_auth.py               Service-to-service JWT (platform-wide shared secret, this module's own inbound protection)
    token_signer.py             This module's own distinct signing key for the scoped tokens it issues
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — roles, identities, tokens, authorize
  schemas/                    Pydantic request/response models
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
