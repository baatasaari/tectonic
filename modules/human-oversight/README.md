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

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
