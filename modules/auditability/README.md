# Auditability — Module 20

The platform-wide, append-only sink for governance-relevant events every
other module emits: conversational handoffs, human-oversight decisions
and overrides, sentinel alerts, graph writes, and anything else a module
chooses to record. Owns tamper-evident storage, filtered querying,
natural-language query translation, and audit-pack export. Full design
doc: [`../../docs/module-20-auditability.md`](../../docs/module-20-auditability.md).

## Layout

```
src/auditability/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                  Pydantic Settings — LLD config schema
  core/
    domain.py                 AuditEventRecord/AuditEventFilter/AuditPackRecord dataclasses
    ports.py                    Repository, LLM Gateway
    fakes.py                     In-memory implementations of every port, for unit tests
    hash_chain.py                  Pure hash-chain functions — canonical_json, compute_entry_hash
    chain_verifier.py               Chain Verifier — walks and re-proves a tenant's chain
    ingestion_service.py             Ingestion Service — the ingest orchestrator
    audit_pack_generator.py           Audit Pack Generator — filtered export + PDF/JSON render
    audit_pack_worker.py               Durable audit-pack worker (Postgres SKIP LOCKED queue)
    nl_query_translator.py              NL Query Translator — LLM Gateway call, validated output
  db/                      SQLAlchemy 2.0 async models + repository (AuditEvent/AuditPack)
  clients/                 Resilient HTTP client for LLM Gateway
  security/                 Service-to-service JWT bearer auth (shared signing key), real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — ingest, list, verify-chain, audit-packs, NL query
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Hash chain, not a blockchain library.** The LLD calls for "immutable
  chained logs with cryptographic tamper-evidence." `core/hash_chain.py`
  implements this directly with stdlib `hashlib` (SHA-256) over a
  canonical JSON serialization of each entry plus the prior entry's hash
  — a single-writer-per-tenant hash chain has no need for a dedicated
  ledger/blockchain library's consensus or distributed-storage machinery.
  `core/chain_verifier.py` walks a tenant's chain and recomputes every
  hash independently; `InMemoryAuditabilityRepository` (the unit-test
  fake) and `SQLAlchemyAuditabilityRepository` both call the exact same
  `compute_entry_hash` function when appending, so the two can never
  silently drift into producing different hashes for identical inputs —
  a real correctness property, not just parallel reimplementations.
- **`source_module` from the JWT, never from the request body.** The
  single most audit-critical field on every entry is read from the
  verified inbound bearer token's `iss` claim (`security/jwt_auth.py`'s
  `caller_service_name`, a module-specific extension of this platform's
  shared `ServiceAuthMiddleware` — see that file's docstring), not from
  any field the caller's JSON body could set. A module cannot
  misattribute an event to a different source, accidentally or
  otherwise.
- **Inconsistent caller payload shapes, tolerated not rejected.** Five
  modules built before this one (Conversational Engine, Graph DB, Human
  Oversight, Regulatory and Compliance, Sentinel Agents) already call
  `POST /v1/auditability/events` with a `tenant_id` key but an
  inconsistent event-type key — some send `event_type`, some send
  `event`. `hash_chain.extract_event_type` normalizes both, falling back
  to `"unknown"` rather than rejecting the write: losing an audit event
  over a naming mismatch is worse than filing it loosely typed. The full
  original payload is still stored unmodified either way.
- **Durable audit-pack generation reuses Module 17's worker design
  exactly**, not a new implementation: `core/audit_pack_worker.py` is the
  same Postgres `SELECT ... FOR UPDATE SKIP LOCKED` queue, time-bounded
  lease, startup recovery sweep, and always-requeue-with-a-single-later-
  poison-pill-check pattern Regulatory and Compliance's own evidence-pack
  worker already proved (a pod restart mid-generation must not lose the
  job) — reused because the correctness property is identical, not
  reinvented.
- **Audit packs are framework-agnostic, unlike Module 17's evidence
  packs.** This module's own "audit pack" (LLD Level 3) is a raw,
  chronologically ordered, integrity-proven export of events matching a
  filter — it does not map controls to any compliance framework's
  clauses. Module 17 is this module's *consumer* (`GET /events?
  control_name=...`, a query five modules already code against), not the
  other way around.
- **NL query translation never reaches raw SQL.** `POST /query`'s LLM
  Gateway call produces a candidate filter; `core/nl_query_translator.py`
  validates it against the exact same `AuditEventFilter` schema the REST
  `GET /events` endpoint uses before it ever reaches the repository — a
  hallucinated field name is rejected with a `422`, never silently
  dropped or (worse) broadening the query beyond what was asked. The
  response always echoes the filter actually used, so a reviewer sees
  what was searched rather than just trusting the answer.
- **`append_event`'s locking is deliberately not `SKIP LOCKED`.** Unlike
  the audit-pack queue's claim (where skipping a locked row to a
  different worker is exactly right), a tenant's event chain requires
  every write to see the immediately preceding one — a concurrent writer
  for the *same* tenant briefly blocks on this lock rather than racing a
  stale read into an incorrect `sequence_number`/`prev_hash`. Different
  tenants never contend, since the lock is scoped per `tenant_id`.
  Proven for real (not just asserted) in
  `tests/integration/test_concurrency_postgres.py`.

## A real bug this surfaced

The first version of `append_event` serialized concurrent writers with
just `SELECT ... FOR UPDATE` on the tenant's last row. That's not enough:
Postgres row locks only apply to rows that already exist, so a brand-new
tenant's *very first* event has no row to lock at all — concurrent first
writers all read "no prior row" and race to insert `sequence_number=1`,
which `tests/integration/test_concurrency_postgres.py` caught for real
against genuine Postgres (a `UniqueViolationError` on
`uq_audit_events_tenant_sequence`), not by reasoning about the SQL in the
abstract. Fixed by taking a Postgres transaction-scoped advisory lock
(`pg_advisory_xact_lock(hashtext(tenant_id))`) before the read, which
serializes regardless of whether any row exists yet; the `FOR UPDATE`
read stays as a secondary guard once a row does exist. The in-memory fake
was never affected — it has no `await` point between reading and
appending, so asyncio's cooperative scheduling can't interleave two
calls mid-operation the way real concurrent DB transactions can.
- **Service-to-service JWT auth.** `security/jwt_auth.py` adds
  shared-signing-key (HS256) bearer auth: `ServiceAuthMiddleware`
  verifies every inbound request's `Authorization: Bearer <JWT>` against
  this module's own `service_name` as the required audience (except
  `/healthz` and `/metrics` — Kubernetes probes and Prometheus scraping
  carry no auth token); `ServiceBearerAuth` (an `httpx.Auth` flow) mints
  a fresh, short-lived (5 min default) token scoped via the `aud` claim
  to LLM Gateway, this module's one outbound dependency. The shared
  secret (`TECTONIC_JWT_SHARED_SECRET`, one Kubernetes Secret referenced
  by every module's Helm chart under this same literal env var name, not
  a per-module-prefixed one) defaults to an obviously-insecure
  placeholder for zero-config local dev/tests; `main.py` logs a startup
  warning if it's still active. This is service-to-service auth for
  inter-module calls, not the platform's external-facing user-auth story
  — a real API gateway/OAuth layer in front of the platform's own entry
  points is a separate, larger concern, out of scope here.
- **Connection pooling and pagination, built in from day one.** Unlike
  the 19 modules built before the platform's enterprise-readiness
  remediation series, this module never had un-tuned defaults to fix:
  `db_pool_size`/`db_max_overflow` are sized against this module's own
  Helm chart's `autoscaling.maxReplicas` (20, since every other module's
  event emission lands here) from the start, and `GET /events` was
  paginated (`limit`/`offset`, default 50/max 200) from its first
  version.

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
