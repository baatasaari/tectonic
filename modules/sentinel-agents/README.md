# Sentinel Agents — Module 15

Watches the platform's own agents at runtime, independent of Guardrails
(individual input/output checks) and Evaluation Framework (quality
scoring). Concerned with behaviour over time and across agents: is this
agent acting outside its normal envelope, and are multiple agents
together producing an emergent problem no single one would trigger
alone. Full design doc:
[`../../docs/module-15-sentinel-agents.md`](../../docs/module-15-sentinel-agents.md).

## Layout

```
src/sentinel_agents/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                AgentBaseline/Alert/InterventionRecord/SwarmCorrelationWindow dataclasses
    ports.py                   Repository, Workflow Engine, Tool Orchestration, Human Oversight, Auditability
    fakes.py                    In-memory implementations of every port, for unit tests
    stats.py                      Welford's online mean/variance algorithm
    baseliner.py                   Behavioural Baseliner — per-agent z-score deviation detection
    swarm_correlation.py            Swarm Correlation Engine — cross-agent windowed correlation
    decision_engine.py               Intervention Decision Engine — alert/autonomous/escalate
    event_processor.py                The orchestrator tying every component together per event
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP clients for Workflow Engine, Tool Orchestration, Human Oversight, Auditability
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — events, alerts, baselines, config
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Agent runtime.** The LLD calls for Google ADK 2.0 `Agent` since
  Sentinels are themselves agents. Following the same precedent as
  Module 1 (Workflow Engine), this is a self-contained implementation
  rather than a dependency on ADK 2.0, which isn't installable/runnable
  in this build environment.
- **Event ingestion.** The LLD calls for `aiokafka` consuming from a
  Kafka/Redpanda event bus. No broker is available in this build
  environment, so `POST /v1/sentinel-agents/events` is a synchronous
  HTTP ingestion endpoint standing in for the Kafka consumer — other
  modules (or a Kafka-to-HTTP bridge in a real deployment) POST events
  to it directly. Every downstream stage (baselining, swarm correlation,
  decision, intervention) is unaffected by this choice; only the
  transport differs.
- **Behavioural baselining.** Implements the LLD's own stated default —
  "statistical process control (rolling mean/variance per agent per
  action type)" — via Welford's online algorithm, with z-score
  thresholds tuned by the `low`/`medium`/`high` sensitivity config. The
  optional isolation-forest tier for higher-volume tenants is a
  documented gap, not implemented.
- **Swarm window state.** The correlation window is held in a single
  long-lived in-process tracker (`SwarmWindowTracker`, constructed once
  in `AppContext`), not a shared store. Correct for a single instance,
  but a multi-replica deployment consuming different Kafka partitions
  would each see only part of the swarm signal — a shared window (Redis,
  or tenant-based partitioning) would be needed for production
  horizontal scale.
- **Tool Orchestration circuit-break target.** The LLD's Decision Engine
  calls "Tool Orchestration's circuit breaker" as an intervention target.
  Module 4 (Tool Orchestration)'s own LLD and API surface never define an
  externally triggerable circuit-break endpoint — its breaker only opens
  from call failures it observes internally. `HTTPToolOrchestrationClient
  .circuit_break()` calls a plausible-but-not-yet-real endpoint and treats
  a failure as best-effort (logged, not raised), the same documented-gap
  pattern used for Long-Term Memory's Graph DB erasure call.
- **`POST /config` runtime overrides.** Accepted for API-surface
  completeness but doesn't persist a per-tenant override in this build —
  configuration is sourced from this module's own YAML/env at startup,
  with `baselining.sensitivity` marked hot-reloadable there.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
