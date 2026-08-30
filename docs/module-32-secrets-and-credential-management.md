# Module 32: Secrets and Credential Management — Complete Module Specification

## Overview and Commercial Value

| Description | Inputs | Outputs | Value | Key Metrics |
|---|---|---|---|---|
| Vaulting, rotation and per-tenant isolation of third-party API keys and credentials | Secret to store, rotation policy | Retrieved secret (scoped), rotation confirmation | Removes a common production security failure mode (hardcoded/shared keys) | Rotation compliance rate, secret access audit completeness |

## Differentiator Features

Baseline (table stakes): a per-tenant secret store with a
create/retrieve/revoke lifecycle.

What makes this module genuinely better:

- **Secrets are actually encrypted at rest, not just stored in a
  restricted table.** `security/envelope_encryption.py` wraps every
  secret value in real authenticated symmetric encryption (`Fernet`,
  from the `cryptography` library) under this module's own
  `secrets_master_key` before it ever reaches Postgres — a stolen
  database dump is ciphertext, not a plaintext credential list.
- **Retrieval is gated by this platform's own real zero-trust
  authorization, not a bespoke access-control layer.** `Secret
  AccessService.retrieve` calls Identity and Access (Module 31)'s own
  real `POST /v1/identity-access/authorize` with a
  `secret:{tenant_id}:{namespace}:read` scope before decrypting
  anything — "Auth decision, scoped token" from the module table isn't
  prose here, it's the literal gate every retrieval passes through,
  live-revocation-checked the same way every other `authorize` call in
  this platform already is.
- **"Secret access audit completeness," the LLD's own key metric, is a
  real, dual-recorded trail.** Every retrieval and rotation is both
  persisted locally (queryable per-secret, even if Auditability is
  down) and emitted as a real event to Auditability (Module 20)'s own
  `POST /v1/auditability/events` — the same real-peer emission pattern
  Identity and Access itself just established, applied here to the
  single most security-sensitive action this platform has: reading a
  credential.
- **Rotation compliance is a real, computed number from real
  timestamps, not a policy document.** `RotationService.
  compliance_rate` divides currently-non-overdue active secrets by
  total active secrets, live, every time it's asked — and
  `list_due_for_rotation` is the concrete surface a scheduler (this
  platform's own durable-jobs infra from Module 17, or an external
  cron) polls to know exactly which secrets need a new value next,
  rather than everyone hoping rotation happened.

## Low-Level Design

### Level 1: Module Overview, Boundaries and Tech Stack

**Purpose.** The platform's per-tenant secret vault: a third-party API
key or credential is stored encrypted at rest, retrieved only through a
real zero-trust authorization check, and rotated on a tracked schedule
with full audit history. Distinct from Identity and Access (Module 31):
that module decides *who* is allowed to do *what* platform-wide; this
module is one of the things worth gating that decision on — it never
reimplements authorization itself, it calls the real one.

**Chosen stack**

| Concern | Choice | Why |
|---|---|---|
| Language/runtime | Python 3.12, FastAPI, SQLAlchemy 2.0 async | Platform consistency |
| Encryption at rest | `cryptography`'s `Fernet` (AES-128-CBC + HMAC, authenticated), keyed by this module's own `secrets_master_key` | A real, standard, audited primitive — not a hand-rolled cipher, not base64 "obfuscation" |
| Access control | Calls Identity and Access's real `POST /v1/identity-access/authorize` | Same "real peer, not invented" convention this platform already established; no second access-control system |
| Audit emission | Calls Auditability's real `POST /v1/auditability/events` on every retrieval and rotation | Same real-peer emission pattern Identity and Access itself established |
| Storage | Postgres | Secrets (ciphertext only), versions, local access log |
| Testing | `pytest` unit tier against an in-memory fake; real-Postgres integration tier | Platform-standard pattern |

**Deployability and testability contract.** Runs standalone against
SQLite for unit tests; the dependency-stub plays both Identity and
Access's `POST /authorize` and Auditability's `POST /events` with
canned, controllable responses, so the full gated-retrieval and
rotation paths are exercised end to end without either real peer
deployed alongside it. Envelope encryption needs no external peer —
pure, deterministic cryptography, exercised directly against the real
cipher in every test tier, not a fake.

### Level 2: Component Architecture and Diagrams

```mermaid
flowchart TB
    subgraph Callers[Platform Modules / Operators]
        C1[Store secret, rotate, revoke]
        C2[Retrieve secret (with a token)]
        C3[Scheduler: which secrets are due?]
    end

    subgraph Secrets[Secrets and Credential Management Module]
        API[FastAPI Layer]
        REG[Secret Registry Service]
        ACCESS[Secret Access Service]
        ROT[Rotation Service]
        CIPHER[Envelope Cipher]
        REPO[(Postgres — secrets, secret_versions, access_records)]
    end

    IDA[Identity and Access<br/>Module 31]
    AUDIT[Auditability<br/>Module 20]

    C1 --> API --> REG --> CIPHER
    REG --> REPO
    C2 --> API --> ACCESS --> IDA
    ACCESS --> CIPHER
    ACCESS --> REPO
    ACCESS --> AUDIT
    C3 --> API --> ROT --> REPO
    ROT --> AUDIT
```

**Sub-components**

| Component | Responsibility | Built on |
|---|---|---|
| Secret Registry Service | Store/list/revoke secret metadata and their first version | Envelope Cipher, own Postgres tables |
| Secret Access Service | The zero-trust-gated retrieval path: authorize, decrypt, log, audit | `clients/identity_access_client.py`, `clients/auditability_client.py`, Envelope Cipher |
| Rotation Service | Creates a new version on rotation, tracks compliance, surfaces what's overdue | Own Postgres tables |

### Level 3: Detailed Design

**Data model**

| Entity | Fields |
|---|---|
| `SecretRecord` | `id`, `tenant_id`, `namespace`, `key_name`, `status` (`active`/`revoked`), `rotation_interval_days`, `last_rotated_at`, `next_rotation_due_at`, `current_version`, `created_at`, `updated_at` |
| `SecretVersionRecord` | `id`, `secret_id`, `version` (int, incrementing), `ciphertext`, `created_at` |
| `SecretAccessRecord` | `id`, `secret_id`, `tenant_id`, `allowed`, `reason`, `accessed_at` — the local mirror of every retrieval attempt, allowed or denied |

**API surface**

| Endpoint | Method | Notes |
|---|---|---|
| `/v1/secrets` | POST | Store: `{namespace, key_name, value, rotation_interval_days}` → metadata only, never echoes `value` |
| `/v1/secrets` | GET | Paginated metadata, filterable by `tenant_id`/`namespace`/`status` |
| `/v1/secrets/{id}` | GET | Metadata only |
| `/v1/secrets/{id}/retrieve` | POST | `{token}` → `{value}` on success; `403` on a denied `authorize` call |
| `/v1/secrets/{id}/rotate` | POST | `{new_value}` → new version, refreshed rotation timestamps |
| `/v1/secrets/{id}/revoke` | POST | `active → revoked` |
| `/v1/secrets/due-for-rotation` | GET | Paginated, filterable by `tenant_id` — the scheduler's own polling surface |
| `/v1/secrets/{id}/access-log` | GET | Paginated `SecretAccessRecord` history for one secret |
| `/v1/secrets/compliance` | GET | `{tenant_id}` → `{compliance_rate, total_active, overdue}` |

**The gated retrieval path.** Fetch the secret's metadata (`404` if
missing, `403` if `revoked`) → call Identity and Access's real
`authorize(token, required_scope="secret:{tenant_id}:{namespace}:read")`
→ deny means `403`, logged and audited exactly like an allow → decrypt
the latest version → log and audit the access → return the plaintext
value. Every branch is logged; only a genuine allow ever reaches
decryption.

### Level 4: Telemetry, Logging, Tracing, Alerting, Configuration and Testing

**Tracing.** `secrets.retrieve` span per retrieval
(`secrets.secret_id`, `secrets.allowed`); `secrets.rotate` span per
rotation (`secrets.secret_id`, `secrets.new_version`).

**Logging.** `structlog` JSON; every denied retrieval and every
`revoke` log at `warning` — real security-relevant signals worth being
able to audit, in addition to the real events emitted to Auditability.

**Metrics (Prometheus)**

| Metric | Type | Labels |
|---|---|---|
| `secrets_access_total` | Counter | `allowed` (secret access audit completeness's raw signal) |
| `secrets_rotations_total` | Counter | `tenant_id` |
| `secrets_rotation_compliance_rate` | Gauge | `tenant_id` (the LLD's own key metric, set on every compliance check) |

**Alerting**

| Alert | Condition | Severity |
|---|---|---|
| SecretsAccessDeniedRateHigh | `secrets_access_total{allowed="False"}` rate > 5 per minute, sustained 5m | Warning |
| SecretsRotationComplianceLow | `secrets_rotation_compliance_rate` < 0.8 for any `tenant_id`, sustained 1h | Warning |

**Configuration**

```yaml
secrets-and-credential-management:
  tenant_id: "<tenant>"
  service_name: "secrets-and-credential-management"
  identity_access_base_url: "http://identity-and-access:8110"
  auditability_base_url: "http://auditability:8090"
  jwt_shared_secret: "dev-insecure-shared-secret-change-me"  # env TECTONIC_JWT_SHARED_SECRET
  secrets_master_key: "dev-insecure-fernet-key-change-me-0000000000000000="  # env SECRETS_MASTER_KEY -- encrypts every secret at rest
```

**Testing**

| Level | Tooling |
|---|---|
| Unit | `pytest` against the in-memory fake, incl. the envelope cipher round-trip (real crypto, no fake), the gated-retrieval allow/deny/revoked matrix, and the rotation/compliance-rate computation as pure-function-shaped tests |
| Integration (isolated) | Real Postgres (dual-path fixture) |
| Contract | `schemathesis` against the REST surface |

**Non-functional targets**

| Attribute | Target |
|---|---|
| `retrieve` latency (p95) | Under 150ms (includes one real `authorize` round trip) |
| Availability | 99.95% |
