# Human Oversight — Module 16

The single system of record for every point where a human is asked to
review, approve, reject or override an agent decision, regardless of
which module raised the request. Owns queueing, notification, decision
capture and override logging; does not itself decide what should
require human review — that's each calling module's responsibility.
Full design doc:
[`../../docs/module-16-human-oversight.md`](../../docs/module-16-human-oversight.md).

## Layout

```
src/human_oversight/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                OversightRequest/Decision/OverrideRecord/NotificationLog dataclasses
    ports.py                   Repository, notification channels, callback dispatcher, Auditability
    fakes.py                    In-memory implementations of every port, for unit tests
    queue_manager.py              Approval Queue Manager — enqueue, claim, expiry sweep
    notification_dispatcher.py     Notification Dispatcher — fans out to configured channels
    decision_capture.py             Decision Capture + Override Logger — decide, callback, audit
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 Real notification channel adapters (Slack/Teams/webhook/SMTP) + callback dispatcher
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — requests, claim, decide
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **Notification channels.** Slack and MS Teams delivery are, under the
  hood, just an HTTP POST to a per-workspace incoming-webhook URL, so
  `SlackNotificationChannel`/`TeamsNotificationChannel`/
  `WebhookNotificationChannel` are genuine, functional adapters given a
  real webhook URL — not stand-ins. `SMTPNotificationChannel` is real
  code too (stdlib `smtplib`), but this build environment has no
  reachable SMTP server, so it isn't exercised end-to-end here — this
  matches the LLD's own Integration testing row ("notification channels
  mocked"), not a deviation from it.
- **Decision callback to the requesting module.** Module 1 (Workflow
  Engine) already has a real, built `POST /instances/{id}/approvals/
  {approval_id}/callback` endpoint — `HTTPDecisionCallbackDispatcher`
  calls it for real when `requesting_module == "workflow_engine"` and
  `requesting_ref` is formatted as `"{instance_id}:{approval_id}"`. No
  other requesting module defines a standard callback endpoint yet in
  this platform's build so far; those get a best-effort generic callback
  (logged, not raised, on failure) — the same documented-gap pattern used
  for Long-Term Memory's Graph DB erasure call and Sentinel Agents' Tool
  Orchestration circuit-break call.
- **Per-tenant notification channel configuration.** The LLD's config
  schema names `notification.channels` as tenant-configurable. This
  build sources it from static YAML/env like the rest of this module's
  config, consistent with how other modules in this platform handle
  config not yet backed by dynamic per-tenant storage.
- **Postgres integration tests** — the repository layer is now also tested
  against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering
  nested-dict/list JSONB round-tripping on `context` and the paired
  `original_agent_proposal`/`human_override_action` columns, a real UUID
  primary key round trip through `get_request`, and a multi-row filtered query
  (`list_pending_expired`) hitting only rows matching tenant, status *and*
  expiry cutoff — none of which SQLite's unit-tier fakes can reliably prove.
  See `tests/integration/conftest.py` for how the Postgres instance is
  obtained. This tier's presence prompted a platform-wide sweep of every
  module's `db/models.py` for the same class of bug: `Mapped[datetime]`
  columns missing `DateTime(timezone=True)` despite the Alembic migration
  already defining them as timestamptz and the domain layer's defaults being
  tz-aware — invisible under SQLite, but a real correctness bug against
  Postgres once a domain default (or an explicit value) is written. Found and
  fixed here too.

- **Pagination on `GET /requests`.** Added `limit`/`offset` query params
  (default 50, max 200) and an `OversightRequestListResponse` envelope
  (`items`/`total`/`limit`/`offset`) — this endpoint previously returned
  every matching row unbounded, a real scaling gap for a tenant with a
  large oversight request history. Ordered by `created_at` descending
  (newest request first) for stable pagination.

- **Connection pooling tuned to replica count.** SQLAlchemy's out-of-
  the-box defaults (`pool_size=5`, `max_overflow=10`) are the same
  regardless of how many pods are running — at this module's own
  `deploy/helm/human-oversight/values.yaml` `autoscaling.maxReplicas: 10`,
  that's up to 150 connections to this module's own Postgres
  instance from this module alone at full autoscale, with no one having
  deliberately decided that number. `db/session.py`'s `make_engine` now
  passes explicit, configurable `pool_size=10` /
  `max_overflow=5` (`db_pool_size`/`db_max_overflow`
  Settings, env-overridable) sized so this module's own steady-state
  total stays at ~100 connections and its full-burst total at ~150,
  even at `maxReplicas`. `pool_recycle=1800s` also avoids stale
  connections behind a cloud LB/proxy's own idle-connection timeout —
  a real, independent gap, not just a replica-count one.

- **Service-to-service JWT auth.** Before this, no module authenticated
  any of its inbound HTTP calls — any process able to reach a module's
  port could call it, and every outbound call this module makes carried
  no credential at all. `security/jwt_auth.py` adds shared-signing-key
  (HS256) bearer auth: `ServiceAuthMiddleware` verifies every inbound
  request's `Authorization: Bearer <JWT>` against this module's own
  `service_name` as the required audience (except `/healthz` and
  `/metrics` — Kubernetes probes and Prometheus scraping carry no auth
  token). `ServiceBearerAuth` (an `httpx.Auth` flow) mints a fresh,
  short-lived (5 min default) token scoped via the `aud` claim to the
  *specific* peer being called on outbound requests `HTTPAuditabilityClient`
  makes, the same fixed-audience-at-construction pattern used everywhere
  else in this platform. `HTTPDecisionCallbackDispatcher` is the one
  exception: its callback target (`requesting_module`) is only known per
  call, not at construction time — a request originating from Workflow
  Engine gets called back differently from one originating from Sentinel
  Agents, decided fresh on every `notify()` call — so it can't bind to one
  fixed `ServiceBearerAuth`. Instead it mints its own token inline inside
  `notify()`, scoping the `aud` claim to that call's `requesting_module`
  (kebab-cased to match this platform's service-name convention, e.g.
  `"workflow_engine"` -> `"workflow-engine"`) on both its Workflow-Engine
  and generic-callback branches. The shared secret
  (`TECTONIC_JWT_SHARED_SECRET`, one Kubernetes Secret referenced by
  every module's Helm chart under this same literal env var name, not a
  per-module-prefixed one) defaults to an obviously-insecure placeholder
  for zero-config local dev/tests; `main.py` logs a startup warning if
  it's still active. This is service-to-service auth for inter-module
  calls, not the platform's external-facing user-auth story — a real API
  gateway/OAuth layer in front of the platform's own entry points is a
  separate, larger concern, out of scope here.

- **Enforces its own subscription entitlement via `EntitlementGateMiddleware`**
  (`security/entitlement_gate.py`) — see Agent Cards' README and the rollout
  playbook doc (`docs/entitlement-gate-rollout.md`) for the shared reference
  implementation. Layered after `ServiceAuthMiddleware` (authenticate, then
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=human-oversight`,
  denying with `402 Payment Required` when the tenant's subscription doesn't
  include this module. It **fails open** if Multi-tenancy is unreachable — a
  deliberate contrast with `ServiceAuthMiddleware`'s zero-trust fail-closed
  posture.

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

- **NUL bytes in raw `Query()` string parameters reaching the database
  unvalidated** (ticket #82's platform-wide sweep, following the same bug
  a real CI run found on Multi-tenancy's and Billing and Metering's own
  contract tiers — see either module's own README for the original
  finding). `GET /v1/human-oversight/requests`'s `tenant_id` and `status`
  never ran through a NUL-byte validator; fixed with
  `_reject_null_byte_query()`. `status` is compared directly against the
  `status` column rather than parsed into a `RequestStatus` enum, so no
  enum-retype fix was needed here (unlike some sibling modules). No
  route-level test file existed for this module before this fix —
  `tests/unit/test_routes_oversight.py` (new) pins just this regression;
  comprehensive route coverage remains a real, separately-scoped gap.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
