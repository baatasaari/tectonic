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
- **Postgres integration tests** — the repository layer is now also
  tested against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering
  nested-dict/list JSONB round-tripping on `context` and the paired
  `original_agent_proposal`/`human_override_action` columns, a real
  UUID primary key round trip through `get_request`, and a multi-row
  filtered query (`list_pending_expired`) hitting only rows matching
  tenant, status *and* expiry cutoff — none of which SQLite's unit-tier
  fakes can reliably prove. See `tests/integration/conftest.py` for how
  the Postgres instance is obtained.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
