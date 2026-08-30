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
    ports.py                    Repository, the two real platform-peer client ports, KeyManagementProvider
    fakes.py                     In-memory implementations of every port, for unit tests
    secret_registry_service.py    Secret Registry — create/get/list/revoke
    secret_access_service.py        Secret Access Service — the zero-trust-gated retrieval path
    rotation_service.py             Rotation Service — rotate, due-for-rotation, compliance rate
  db/                      SQLAlchemy 2.0 async models + repository (Secret/SecretVersion/SecretAccess)
  clients/                 Resilient HTTP clients to Identity and Access + Auditability
  security/
    jwt_auth.py               Service-to-service JWT (platform-wide shared secret, this module's own inbound protection)
    openapi_security.py       Real OpenAPI security scheme declaration
    envelope_encryption.py      Real envelope encryption (Fernet) -- a fresh data key per encrypt call
    key_management.py            KeyManagementProvider implementations: LocalStaticKeyManagementProvider (dev/test) + VaultTransitKeyManagementProvider (real HashiCorp Vault Transit)
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — secrets, retrieve, rotate, revoke, compliance
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Encryption at rest is real, not a TODO — and now real *envelope*
  encryption backed by a managed KMS, not one static key.** Every
  value this module ever stores passes through `EnvelopeCipher.encrypt`
  (`Fernet` — AES-128-CBC + HMAC); `decrypt` only ever runs after a
  real `authorize` check has already passed. Previously the whole
  cipher was keyed by one static `secrets_master_key` living in this
  module's own config — meaning compromising this module's config
  compromised every secret it had ever stored, with no external
  root-of-trust, no independent audit trail on the key itself, and no
  rotation story. Now every `encrypt` call generates a fresh, random
  32-byte data key, encrypts the value with it once, and returns that
  data key *wrapped* by a `KeyManagementProvider` (`security/
  key_management.py`); `decrypt` unwraps the version's own wrapped key
  first, then decrypts. Each `SecretVersionRecord` carries its own
  wrapped data key, so one compromised ciphertext never exposes any
  other version's key, and the provider's actual root key never
  leaves the provider. Two implementations behind that one interface:
  - `LocalStaticKeyManagementProvider` (`SECRETS_KMS_PROVIDER=local`,
    the default): wraps each data key with the same static local
    Fernet key the old design used directly -- structurally the
    *previous* design, demoted to an explicitly-flagged, zero-config
    dev/test fallback. `main.py` logs a loud startup warning whenever
    this is what's actually wired, the same posture
    `jwt_shared_secret_is_insecure_default` already takes elsewhere in
    this platform.
  - `VaultTransitKeyManagementProvider` (`SECRETS_KMS_PROVIDER=vault`):
    a real HashiCorp Vault Transit secrets engine integration — Vault's
    own `datakey`/`decrypt` endpoints generate and unwrap every data
    key, so the true root key lives in Vault and inherits its access
    control, audit logging, and rotation machinery. Plain `httpx`
    through `ResilientHTTPClient` (retry + circuit breaker), not the
    `hvac` SDK, consistent with this platform's small-hand-written-
    adapter convention elsewhere. No live Vault server is reachable
    from this sandbox — `tests/unit/test_vault_key_management.py`
    verifies this class against a respx-mocked transport using Vault's
    real documented request/response shapes (the same "real client,
    mocked transport" constraint and answer Identity and Access's OIDC
    verifier hit); a genuine `vault server -dev` instance is the
    honest verification path a real deployment takes next, not
    something fabricated here. AWS KMS/GCP KMS are the same shape
    behind the same port, unbuilt.
- **Two distinct secrets for two distinct trust boundaries.** This
  module's own inbound API is still protected by the platform-wide
  `TECTONIC_JWT_SHARED_SECRET` every module shares; encryption at rest's
  outer wrapping layer is keyed by a completely separate secret
  (`secrets_master_key` for the local provider, Vault's own root key for
  the Vault provider). Compromising one never compromises the other.
- **A KMS/Vault outage denies access, it doesn't crash the request.**
  `SecretAccessService.retrieve` catches `KeyManagementError`
  specifically (an unreachable Vault, a revoked key version) and
  records/returns a clean denial (`"key management provider
  unavailable"`) rather than letting it bubble into a 500 — the same
  "record and deny, never silently succeed or hard-crash" posture a
  failed `authorize` call already gets.
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

- **NUL bytes/invalid enum values reaching the database or crashing
  unhandled** (ticket #82's platform-wide sweep, following the same bug
  a real CI run found on Multi-tenancy's and Billing and Metering's own
  contract tiers — see either module's own README for the original
  finding). `GET ""` (list secrets)'s `tenant_id`/`namespace`,
  `GET /due-for-rotation`'s `tenant_id`, and `GET /compliance`'s
  `tenant_id` never ran through a NUL-byte validator; fixed with
  `_reject_null_byte_query()`. The list route's own `status` was a bare
  `str` hand-converted to `SecretStatus`, raising an unhandled
  `ValueError` (500) for any non-member string — now typed
  `SecretStatus` directly so FastAPI/Pydantic itself rejects an invalid
  value with a clean 422.

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
