# Secrets and Credential Management — Module 32

A per-tenant secret vault: every value is encrypted at rest before it
ever touches Postgres, and the one path that returns a plaintext value
back to a caller is gated on a real, live zero-trust `authorize` call to
Identity and Access (Module 31) — not a bare API key or a shared vault
token. Every retrieval attempt, allowed or denied, is dual-recorded: a
local `SecretAccessRecord` row (always) and a best-effort real event to
Auditability (Module 20). Rotation compliance is tracked as a real,
computed Prometheus Gauge, not just a documented aspiration. Full design
doc: [`../../docs/module-32-secrets-and-credential-management.md`](../../docs/module-32-secrets-and-credential-management.md).

## Layout

```
src/secrets_and_credential_management/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                  Pydantic Settings — LLD config schema
  core/
    domain.py                 SecretRecord/SecretVersionRecord/SecretAccessRecord, the secret lifecycle state machine
    ports.py                    Repository, the two real platform-peer client ports
    fakes.py                     In-memory implementations of every port, for unit tests
    secret_registry_service.py    Secret Registry — create/get/list/revoke
    secret_access_service.py        Secret Access Service — the zero-trust-gated retrieval path
    rotation_service.py             Rotation Service — rotate, due-for-rotation, compliance rate
  db/                      SQLAlchemy 2.0 async models + repository (Secret/SecretVersion/SecretAccess)
  clients/                 Resilient HTTP clients to Identity and Access + Auditability
  security/
    jwt_auth.py               Service-to-service JWT (platform-wide shared secret, this module's own inbound protection)
    openapi_security.py       Real OpenAPI security scheme declaration
    envelope_encryption.py      This module's own distinct encryption-at-rest key (Fernet)
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — secrets, retrieve, rotate, revoke, compliance
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Encryption at rest is real, not a TODO.** Every value this module
  ever stores passes through `EnvelopeCipher.encrypt` (`Fernet` —
  AES-128-CBC + HMAC) first; `decrypt` only ever runs after a real
  `authorize` check has already passed. `security/envelope_encryption.py`
  is pure, deterministic cryptography — no I/O, so unlike this module's
  real HTTP peer clients it needs no fake for unit tests.
- **Two distinct secrets for two distinct trust boundaries.** This
  module's own inbound API is still protected by the platform-wide
  `TECTONIC_JWT_SHARED_SECRET` every module shares; encryption at rest is
  keyed by this module's own dedicated `secrets_master_key`. Compromising
  one never compromises the other.
- **Retrieval is gated by a real zero-trust check, not a local
  permission table.** `SecretAccessService.retrieve` calls Identity and
  Access's own real `POST /v1/identity-access/authorize` with scope
  `secret:{tenant_id}:{namespace}:read` — the same live-revocation-aware
  gate every other authorize call in this platform goes through.
- **The secret lifecycle is one-way.** Unlike this platform's other
  active↔suspended state machines, a revoked secret can never be
  reactivated — `_LEGAL_TRANSITIONS` only ever allows `ACTIVE →
  REVOKED`.
- **Rotation compliance is a real computed Gauge.** `secrets_rotation_
  compliance_rate` is set from an actual `(total_active, overdue)`
  query on every `/v1/secrets/compliance` call — with zero active
  secrets, the LLD's own insufficient-data-over-fabrication principle
  applies: the report says `None`, never a fabricated 1.0.
- **`rotate` only records that a new value exists.** Actually turning
  over the credential at the third-party system of record is the
  caller's job; `list_due_for_rotation` is what a scheduler polls to
  know what still needs that real-world rotation done.

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
