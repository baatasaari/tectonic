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
  security/                 Service-to-service JWT bearer auth (shared signing key)
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — requests, claim, decide
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

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

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
