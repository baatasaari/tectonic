# Tool Orchestration — Module 4

The single point through which every agent action against an external tool
passes: discovery, invocation, retries, reliability scoring and (for
narrow, well-specified gaps) guarded synthesis of new tools from existing
primitives. Agents never call a third-party API directly. Full design doc:
[`../../docs/module-04-tool-orchestration.md`](../../docs/module-04-tool-orchestration.md).

## Layout

```
src/tool_orchestration/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                ToolDefinition/ToolInvocation/ReliabilityScore/CircuitBreakerState dataclasses
    ports.py                   Repository, circuit breaker store, MCP adapter, synthesis dependencies
    fakes.py                    In-memory implementations of every port, for unit tests
    circuit_breaker.py           Circuit Breaker — pure state-transition logic
    reliability_scorer.py         Reliability Scorer — EMA-based rolling success rate
    retry_manager.py               Retry Manager — per-tool backoff policy
    tool_synthesis.py               Tool Synthesis Engine — guarded, never self-activates
    orchestration_service.py         The invocation orchestrator (this module's "scheduler")
  db/                      SQLAlchemy 2.0 async models + repository (ToolDefinition/Invocation/ReliabilityScore)
  clients/                 Redis circuit breaker store, MCP HTTP adapter, LLM Gateway/Guardrails/Sentinel clients
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI routers — discovery, invoke, synthesise, approve
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **MCP protocol.** The LLD names the official `mcp` Python SDK. `clients/
  mcp_http_client.py` implements `MCPClientAdapter` as a generic
  JSON-RPC-2.0-over-HTTP client instead — JSON-RPC is MCP's wire-level
  shape regardless of transport variant. Swapping in the real SDK (stdio/
  SSE/streamable-HTTP transports, capability negotiation) means
  implementing the same Protocol against it, without touching the circuit
  breaker, retry manager or reliability scorer that drive it — same
  boundary Module 1 draws around ADK and Module 3 draws around LiteLLM.
- **Circuit breaker state is Redis-only.** Per the LLD's stack table, it's
  never persisted to Postgres — losing it just means every tool starts
  "closed" again, which is the safe direction to fail in.
- **Reliability scoring.** Uses an exponential moving average rather than a
  stored rolling-window history, so "real-time update on each invocation"
  (LLD component table) doesn't require accumulating a history buffer per
  tool.
- **Synthesis safety.** `ToolSynthesisEngine` never sets a tool's status to
  `active` — only `POST /tools/{id}/approve` does, and
  `synthesis.require_sentinel_approval` cannot be disabled while synthesis
  is enabled (enforced at config load, not just documented). A synthesised
  tool always passes through Guardrails and gets a Sentinel Agents review
  ticket before it can ever be approved.
- **Postgres integration tests** — the repository layer is now also tested
  against a real Postgres (`tests/integration/`, opt-in via
  `TECTONIC_TEST_POSTGRES_URL` or Docker+testcontainers), covering the
  `ToolDefinition.schema` JSONB round trip, a real UUID primary key, a
  multi-row `list_tool_definitions` query filtered by tenant and status, and
  an upsert-style reliability-score update that must touch only the targeted
  tool's row — all things SQLite's unit-tier fakes can't reliably prove. See
  `tests/integration/conftest.py` for how the Postgres instance is obtained.
  This tier's presence prompted a platform-wide sweep of every module's
  `db/models.py` for the same class of bug: `Mapped[datetime]` columns missing
  `DateTime(timezone=True)` despite the Alembic migration already defining
  them as timestamptz and the domain layer's defaults being tz-aware —
  invisible under SQLite, but a real correctness bug against Postgres once a
  domain default (or an explicit value) is written. Found and fixed here too.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, Redis, dependency-stub
```
