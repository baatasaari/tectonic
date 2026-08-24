# Agent Marketplace / Registry — Module 24

The platform's internal catalogue of built agents: a team publishes a
listing referencing an existing Agent Card (Module 23), it goes through
an explicit governance approval before appearing in search, and every
genuine reuse by a different team is tracked. Full design doc:
[`../../docs/module-24-agent-marketplace.md`](../../docs/module-24-agent-marketplace.md).

## Layout

```
src/agent_marketplace/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                  Pydantic Settings — LLD config schema
  core/
    domain.py                 ListingRecord/UsageEventRecord dataclasses, the governance state machine
    ports.py                    Repository, Agent Cards client
    fakes.py                     In-memory implementations of every port, for unit tests
    governance_service.py         Governance Service — submit/approve/reject/deprecate
    catalogue_sync_service.py      Catalogue Sync Service — wholesale-refresh the card snapshot
    catalogue_service.py            Catalogue Service — search, reuse_count-first ranking
    usage_tracking_service.py        Usage Tracking Service — record-usage, reuse metrics
  db/                      SQLAlchemy 2.0 async models + repository (Listing/UsageEvent)
  clients/                 Resilient HTTP client to Agent Cards
  security/                 Service-to-service JWT bearer auth (shared signing key)
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — submit, approve/reject/deprecate, sync, search, record-usage
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **A real governance gate, not a self-publish list.** `GovernanceService`
  enforces the legal-transition table in `core/domain.py`
  (`is_legal_transition`) — `pending_review → published` needs an
  explicit `approve`; anything not in that table (approving an
  already-published listing, rejecting a deprecated one) raises
  `InvalidTransitionError`, surfaced as `409 Conflict`.
- **Reuse is measured, not asserted.** `reuse_count` is recomputed from
  the real `agent_marketplace_usage_events` log on every
  `record-usage` call (`count_usage_events`), never just incremented —
  the denormalized counter and the event log it's derived from can
  never drift apart. Catalogue search sorts by `reuse_count` descending
  by default, ties broken by the snapshotted `trust_score` — a team
  finds the agent others have actually reused first.
- **Card data is snapshotted, never owned.** `CatalogueSyncService`
  fetches the referenced card from Agent Cards (Module 23)'s own `GET
  /agent-cards/{id}` and wholesale-replaces the listing's
  name/description/skills/trust_score snapshot — the same "always a
  replace, never a merge" convention MCP's own Capability Sync Service
  established. Agent Cards remains the sole owner of the capability
  manifest and its trust score; this module only reads and snapshots.
- **External monetisation is a documented placeholder, not a half-built
  feature.** `external_listing_enabled` is a real boolean field with no
  billing/payment logic behind it — that's Module 33 (Billing and
  Metering)'s job once it exists, matching the module table's own
  "(future)" qualifier rather than half-implementing it here.
- **No reviewer-role enforcement yet, and that's a documented choice.**
  `approve`/`reject` are gated the same as every other route (this
  platform's shared-secret JWT) but not by a distinct reviewer role —
  Identity and Access (Module 27) is where that belongs once it exists;
  the state machine itself doesn't need to change shape to adopt it,
  only who's allowed to call it does.
- **Connection pooling and pagination, built in from day one.** Sized
  against this module's own Helm chart's `autoscaling.maxReplicas` from
  the start (this platform's standard formula), and `GET /listings` is
  paginated (`limit`/`offset`, default 50/max 200) from its first
  version.

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
