# Tectonic — Agentic AI Platform

[![CI](https://github.com/baatasaari/tectonic/actions/workflows/ci.yml/badge.svg)](https://github.com/baatasaari/tectonic/actions/workflows/ci.yml)

A cloud-agnostic platform for building, running and governing agentic AI
applications: 34 modules spanning orchestration/runtime, intelligence,
data, memory, governance/safety, quality/trust and interoperability. Full
module catalogue: [`docs/agentic-platform-final-module-table.md`](docs/agentic-platform-final-module-table.md).

## Status

| Module | Status |
|---|---|
| 1 — Workflow Engine | Built — [`modules/workflow-engine`](modules/workflow-engine) |
| 2 — Conversational Engine | Built — [`modules/conversational-engine`](modules/conversational-engine) |
| 3 — LLM Gateway | Built — [`modules/llm-gateway`](modules/llm-gateway) |
| 4 — Tool Orchestration | Built — [`modules/tool-orchestration`](modules/tool-orchestration) |
| 5 — Intent Detection | Built — [`modules/intent-detection`](modules/intent-detection) |
| 6 — Agentic RAG | Built — [`modules/agentic-rag`](modules/agentic-rag) |
| 7 — Context Engineering | Built — [`modules/context-engineering`](modules/context-engineering) |
| 8 — Data Source Plugins | Built — [`modules/data-source-plugins`](modules/data-source-plugins) |
| 9 — Knowledge Base | Built — [`modules/knowledge-base`](modules/knowledge-base) |
| 10 — Vector DB | Built — [`modules/vector-db`](modules/vector-db) |
| 11 — Graph DB | Built — [`modules/graph-db`](modules/graph-db) |
| 12 — Short-Term Memory | Built — [`modules/short-term-memory`](modules/short-term-memory) |
| 13 — Long-Term Memory | Built — [`modules/long-term-memory`](modules/long-term-memory) |
| 14 — Guardrails | Built — [`modules/guardrails`](modules/guardrails) |
| 15 — Sentinel Agents | Built — [`modules/sentinel-agents`](modules/sentinel-agents) |
| 16 — Human Oversight | Built — [`modules/human-oversight`](modules/human-oversight) |
| 17 — Regulatory and Compliance | Built — [`modules/regulatory-compliance`](modules/regulatory-compliance) |
| 18 — Evaluation Framework | Built — [`modules/evaluation-framework`](modules/evaluation-framework) |
| 19 — Observability | Built — [`modules/observability`](modules/observability) |
| 20 — Auditability | Built — [`modules/auditability`](modules/auditability) |
| 21 — MCP | Built — [`modules/mcp`](modules/mcp) |
| 22 — A2A | Built — [`modules/a2a`](modules/a2a) |
| 23 — Agent Cards | Built — [`modules/agent-cards`](modules/agent-cards) |
| 24 — Agent Marketplace / Registry | Built — [`modules/agent-marketplace`](modules/agent-marketplace) |
| 25 — LLMOps | Built — [`modules/llmops`](modules/llmops) |
| 26–34 | Not yet started |

Each module is designed, built and tested independently (its own repo-style
subtree under `modules/`, own README, own CI-shaped test tiers), then
integrated. See a module's low-level design doc under `docs/` before
building against it.

## Enterprise-readiness hardening

A dedicated review pass across all 19 built modules — gaps, technical
depth, edge cases, and custom code that open-source frameworks could
replace — landed as a series of six independent, foundational-risk-first
branches/PRs, each scoped to one concern so it could be reviewed and
merged on its own:

| # | Branch | Scope | Status |
|---|---|---|---|
| 1 | `claude/resiliency-retries` | Retries + circuit breakers on every outbound HTTP call | Built — merged |
| 2 | `claude/postgres-integration-tests` | Repository layer tested against a real Postgres, not just SQLite | Built — merged |
| 3 | `claude/durable-background-jobs` | Module 17's evidence-pack generation surviving a pod restart | Built — merged |
| 4 | `claude/pooling-and-pagination` | Connection pooling tuned to Helm replica counts + pagination on list endpoints | Built — merged |
| 5 | `claude/ci-cd-pipeline` | Lint + test gating via GitHub Actions | Built — merged |
| 6 | `claude/jwt-service-auth` | Shared-signing-key service-to-service bearer auth | Built (this branch) |

**Branch 1 — resiliency.** Every module gets a `ResilientHTTPClient` base
class (`clients/resilience.py`) built on real, off-the-shelf libraries —
`tenacity` for exponential-backoff retry, `aiobreaker` for a proper
Release-It!-pattern circuit breaker — not hand-rolled equivalents. Every
one of the ~50 client classes across the platform's `clients/http_clients.py`
files now retries network failures and 5xx responses (never 4xx) and
opens its breaker after repeated failures, so a struggling peer gets a
break instead of a retry storm and callers fail fast instead of piling up
against a peer that's already down. LLM Gateway's real provider-calling
path (`http_provider_client.py`) gets its own per-provider breaker, so one
provider being down never blocks calls to a different one. Verified with
a live reproduction, not just wired and assumed to work: confirmed retry
count on a flaky-then-recovers backend, confirmed zero retries on a 4xx,
and confirmed the breaker actually opens after repeated failures and then
short-circuits without a further network call.

**Branch 2 — real-Postgres integration tests.** 17 of the 19 built
modules (all but Vector DB, which is Qdrant-only with no SQLAlchemy/
Postgres usage, and Short-Term Memory, whose Redis backend is already
covered by `fakeredis`-based unit tests) now have a `tests/integration/`
tier exercising the real `SQLAlchemy*Repository` against genuine Postgres
— not part of the default `pytest` run, opt-in via either
`TECTONIC_TEST_POSTGRES_URL` (an admin connection string to an
already-running Postgres; the fixture creates and drops an isolated
database per test-module run) or Docker + `testcontainers` as a
zero-config fallback, skipping the whole tier cleanly when neither is
available. Each module's suite targets something SQLite's unit tier can't
reliably prove: real JSONB list/dict round-tripping with exact type and
order preservation, real UUID primary keys, and multi-row update/filter
queries hitting only the intended rows.

Actually running these for real — several had never executed against a
genuine Postgres before, including one written earlier in this project
that only supported a Docker-only fixture — surfaced a real, platform-wide
schema-drift bug: in every one of those 17 modules, one or more
`Mapped[datetime]` columns in `db/models.py` were missing
`DateTime(timezone=True)`, even though the corresponding Alembic
migration already defines the column as `timestamptz` and the domain
layer's own defaults are timezone-aware (`datetime.now(UTC)`). SQLite
never enforces the mismatch, so it was invisible in the unit tier; against
real Postgres, asyncpg rejects the write outright
(`can't subtract offset-naive and offset-aware datetimes`) the moment a
tz-aware value is written to what it believes is a naive column. Fixed
across all 17 modules' `db/models.py`, with regression tests added where
the integration suite already exercised the affected column.

**Branch 3 — durable background jobs.** Module 17 (Regulatory and
Compliance)'s evidence-pack generation used to run as an in-process
FastAPI `BackgroundTasks` job — genuine async work, but non-durable: a
pod restart between the `202 Accepted` response and the background task
finishing left the pack permanently stuck at `status=generating`, with
nothing else ever picking the job back up. Fixed with a Postgres-backed
job queue (`core/evidence_worker.py`'s `EvidencePackWorker`), reusing the
`evidence_packs` table itself as the queue: an asyncio poll loop claims
pending packs via `SELECT ... FOR UPDATE SKIP LOCKED`, so multiple worker
instances/pods can poll the same table concurrently without ever
double-claiming a row; each claim gets a time-bounded lease so a crash
mid-generation is recovered automatically once the lease expires, with no
separate liveness check; a startup recovery sweep force-expires every
held lease immediately so anything left mid-flight by a now-dead previous
process instance is reclaimed on the very next poll tick; and a
transient generation failure is requeued for retry, with a
`worker_max_attempts` ceiling so a permanently-broken job stops being
retried forever instead of spinning indefinitely. The one property here
that neither SQLite nor an in-memory fake can prove for real —
concurrent claims never double-claiming the same row — is proven against
a genuine Postgres instance in
`modules/regulatory-compliance/tests/integration/test_evidence_worker_postgres.py`.

**Branch 4 — connection pooling + pagination**, two parts:

- **Connection pooling.** SQLAlchemy's out-of-the-box async engine
  defaults (`pool_size=5`, `max_overflow=10`) applied identically
  everywhere regardless of how many pods are actually running — at each
  module's own Helm chart's `autoscaling.maxReplicas` (10/20/30
  depending on the module), that meant up to 150–450 connections to a
  single module's own Postgres instance from that module alone at full
  autoscale, with no one having deliberately decided the number. Across
  all 17 Postgres-backed modules, `db/session.py`'s `make_engine` now
  passes explicit `pool_size`/`max_overflow`/`pool_timeout`/
  `pool_recycle`, computed per module from its own `maxReplicas` so
  steady-state stays around 100 connections and full-burst around 150
  even at max autoscale, plus `pool_recycle=1800s` everywhere to avoid
  stale connections behind a cloud LB/proxy's own idle timeout — a real,
  independent gap. All four values are now env-overridable Settings
  fields, with a regression test per module asserting `make_engine`
  actually applies them.
- **Pagination.** Audited every list-returning API endpoint platform-wide
  (15 found across 12 modules); added `limit`/`offset` query params
  (default 50, max 200) and a `<Resource>ListResponse` envelope
  (`items`/`total`/`limit`/`offset`) to the ones that were genuinely
  unbounded growing lists. A handful were deliberately left unpaginated
  — llm-gateway's `GET /providers` (a small, fixed, admin-configured
  set) and long-term-memory's `POST /query` (already bounded via its own
  `top_k` ranking) — each justified in a code comment and its module's
  README, not silently skipped. Where a list method is also called
  internally by core logic needing the *complete* set (regulatory-
  compliance's crosswalk/coverage calculation, workflow-engine's
  instance-detail view embedding its full step list), those call sites
  pass an effectively-unbounded internal page size rather than silently
  truncating to the API's default page.

**Branch 5 — CI/CD.** `.github/workflows/ci.yml` — before this,
`.github/workflows/` was empty: nothing gated a push or PR on lint or
tests actually passing. A single workflow, one job per module in a
`fail-fast: false` matrix (so one module's failure never hides
another's), runs on every push/PR to any `claude/**` branch:

- `ruff check src tests`, then `pytest tests/unit -v` — every module,
  every push. A `postgres:16-alpine` service container is always
  available; any module whose `tests/integration/` directory exists (the
  real-Postgres tier from branch 2/6, landing module-by-module as that
  PR and this remediation series merge) gets it run for real too, gated
  purely by "does this directory have files" — no workflow edit needed
  as more modules grow that tier.
- A final `CI` job aggregates all 19 module jobs behind one stable check
  name, so branch protection can require a single check rather than 19
  individual (and shifting, as modules are added) job names.

**Branch 6 — JWT bearer auth (final).** Before this, no module
authenticated any of its inbound HTTP calls — any process able to reach a
module's port could call it, and every outbound call a module makes to a
peer carried no credential at all. Every one of the 19 built modules now
has:

- **`security/jwt_auth.py`** (identical pattern across all 19 modules,
  first built and fully verified on Module 17 as the reference
  implementation): `mint_service_token`/`verify_service_token` (pure
  HS256 functions), `ServiceBearerAuth` (an `httpx.Auth` flow attaching a
  fresh, audience-scoped bearer token to every outbound request an HTTP
  client makes), and `ServiceAuthMiddleware` (verifies every inbound
  request's bearer token against the module's own `service_name` as the
  required audience — except `/healthz` and `/metrics`, which Kubernetes
  probes and Prometheus scraping reach with no auth token).
- **Audience-scoped tokens**: minted with an `aud` claim naming the
  specific peer being called, via each module's own outbound HTTP client
  classes wired to their real target — e.g. Workflow Engine's LLM Gateway
  client mints a token audienced to `llm-gateway`, its Guardrails client
  one audienced to `guardrails`, and so on across ~45 client classes
  platform-wide. A token minted to call one peer is rejected if replayed
  against a different one, limiting a leaked/intercepted token's blast
  radius to the one peer it was meant for.
- **One genuinely shared secret**: `TECTONIC_JWT_SHARED_SECRET` — a
  single, non-module-prefixed env var name every module's config reads
  via a pydantic `Field(validation_alias=...)`, so every Helm chart
  injects the same Kubernetes Secret under this same literal name rather
  than 19 separately-configured ones. Defaults to an obviously-insecure
  placeholder for zero-config local dev/tests; every module logs a
  startup warning if it's still active in a running process.
- **Deliberate exclusions, documented not silent**: a handful of HTTP
  clients call systems outside this platform's shared-secret trust
  boundary — llm-gateway's real external LLM provider calls, tool-
  orchestration's arbitrary third-party MCP tool servers, data-source-
  plugins' external Airbyte/PyAirbyte-style connector runtime — each left
  unwired with a code comment explaining why, not silently skipped.
- **One genuine special case**: human-oversight's decision-callback
  dispatcher calls back to whichever module raised the original oversight
  request — a target only known per-call, not at client-construction
  time — so it mints a token scoped to that call's specific target
  inline in `notify()`, instead of the fixed-audience pattern every other
  client uses, with its own dedicated tests.

Full regression: all 19 modules' unit tiers green, **648 tests total**
(up from 517 before this branch — 131 new, covering mint/verify
round-trips, middleware accept/reject behavior for every failure mode,
and the outbound `ServiceBearerAuth` flow, plus human-oversight's
dynamic-audience dispatcher), `ruff check` clean everywhere. Every
module's reference implementation was additionally verified live against
a real `TestClient`, not just its own unit tests in isolation:
`/healthz`/`/metrics` reachable with no token, a real protected route
rejecting a missing/wrong-audience/wrong-secret/expired/non-Bearer token
and accepting a valid one.

This is service-to-service auth for inter-module calls, not the
platform's external-facing user-auth story — a real API gateway/OAuth
layer in front of the platform's own entry points is a separate, larger
concern, out of scope for this fix.

## Repository layout

```
docs/                          Low-level design specs, the full module table
modules/
  workflow-engine/               Module 1 — see its own README for details
  conversational-engine/          Module 2
  llm-gateway/                     Module 3
  tool-orchestration/               Module 4
  intent-detection/                  Module 5
  agentic-rag/                        Module 6
  context-engineering/                 Module 7
  data-source-plugins/                   Module 8
  knowledge-base/                          Module 9
  vector-db/                                 Module 10
  graph-db/                                    Module 11
  short-term-memory/                             Module 12
  long-term-memory/                                Module 13
  guardrails/                                        Module 14
  sentinel-agents/                                     Module 15
  human-oversight/                                       Module 16
  regulatory-compliance/                                   Module 17
  evaluation-framework/                                      Module 18
  observability/                                               Module 19
  auditability/                                                  Module 20
  mcp/                                                              Module 21
  a2a/                                                                Module 22
  agent-cards/                                                          Module 23
  agent-marketplace/                                                      Module 24
  llmops/                                                                   Module 25
```

## Cross-module integration, once deployed together

Every module talks to its dependencies through its own `dependency_stub_base_url`
config knob today (pointed at a lightweight stub service that ships with
each module — see each module's `stubs/dependency-stub/`), so every module
builds, runs and is fully unit-tested standalone. Deploying more than one
module together means pointing each one's client config at the real peer
module's base URL instead of its stub — no code changes required, since
every external dependency sits behind a Protocol port with an HTTP adapter
already implemented. LLM Gateway (Module 3) is the most widely depended-on
peer so far: Conversational Engine, Tool Orchestration, Intent Detection,
Agentic RAG, Context Engineering and now Vector DB (for embeddings) all
call out to it (completion, classification, groundedness/reformulation,
summarisation, or embedding generation, depending on the module). The
Data Layer group added in this batch chains together too: Knowledge Base
depends on Vector DB (embedding + storage) and Graph DB (entity
extraction), and Agentic RAG's Hybrid Retriever is a natural future
caller of Vector DB once wired up; Data Source Plugins feeds
document-shaped data to Knowledge Base and structured query results
directly to Tool Orchestration.

Vector DB is the one module built against a real instance of its LLD's
named technology rather than a lightweight stand-in: `qdrant-client`
genuinely runs embedded and in-memory with no server process
(`AsyncQdrantClient(location=":memory:")`), so its "Deployability and
Testability Contract" is met literally, without a fallback implementation
to document.

The Memory group closes out this batch: Short-Term Memory (session-
scoped, Redis-backed) and Long-Term Memory (cross-session, Postgres-
backed) both sit beneath Conversational Engine and Context Engineering
for prompt assembly, and Long-Term Memory itself now delegates real
work to two peers built in this same session — Vector DB for semantic
memory and Graph DB for procedural memory — via HTTP clients that target
their actual API surfaces rather than placeholders. That integration
surfaced a genuine gap worth flagging: Graph DB's own LLD doesn't yet
define a delete endpoint, so Long-Term Memory's right-to-erasure flow
treats a Graph DB deletion call as best-effort today (see
`modules/long-term-memory/README.md`).

The Governance/Safety group added in this batch is where cross-module
wiring stops being aspirational: Sentinel Agents' autonomous pause/
terminate calls and Human Oversight's decision callback for
Workflow-Engine-originated requests both target Module 1's actual,
already-built endpoints (`/instances/{id}/pause`, `/terminate`, and
`/instances/{id}/approvals/{approval_id}/callback`), verified by reading
Workflow Engine's own route source rather than assumed from the LLD —
the same "real peer, not a stub" pattern as Vector DB's embedded
qdrant-client. Guardrails, Sentinel Agents and Human Oversight also form
their own triangle: a Guardrails red-team run alerts Sentinel Agents on
any policy bypass, and both modules escalate into Human Oversight's
approval queue when an autonomous decision needs a person. Everything
else these three modules call — Tool Orchestration's circuit-breaker,
non-Workflow-Engine oversight callbacks — remains a documented
best-effort gap, logged on failure rather than raised, until those
peers grow the matching endpoints.

This batch's Quality/Trust-adjacent additions round out that picture.
Regulatory and Compliance is the crosswalk sitting on top of the modules
already built: its bundled default mapping table maps controls this
platform's own Human Oversight, Guardrails, Sentinel Agents and Workflow
Engine already implement to EU AI Act, NIST AI RMF, ISO 42001 and DORA
clauses, and its evidence packs are real generated PDFs (`fpdf2`), not a
text stand-in. Evaluation Framework and Observability both depend on LLM
Gateway the same way every other module does (LLM-as-judge scoring,
reasoning-trace narrative reconstruction) — and Observability's Cost
Attribution Joiner is a second instance of the "real peer, not invented"
pattern: it reads the exact `gen_ai.usage.input_tokens`/`output_tokens`
and `llm_gateway.cost` span attributes LLM Gateway's own
`telemetry/tracing.py` already documents emitting, a genuine cross-module
telemetry contract rather than a guessed shape. Auditability (Module 20,
not yet built) is the one dependency all three of this batch's modules
gesture at without a real peer to call yet — Regulatory and Compliance's
control-event ingestion and Evaluation Framework's/Observability's
Postgres-backed "other modules poll our API for scores/traces" pattern
are both explicitly designed to keep working once it exists, documented
as such in each module's README.

**Post-review corrections to this batch.** Three gaps raised in review of
Modules 17-19 turned out to be real, not just documentation debt, and are
fixed as of this batch's latest commit:

1. **GDPR was missing from Regulatory and Compliance's crosswalk table.**
   Not a deliberate scoping decision — added, mapped against four
   controls this platform already implements (Long-Term Memory's
   right-to-erasure flow → Art.17, Guardrails' PII redaction →
   Art.5(1)(c)/Art.25, Human Oversight's approval queue → Art.22,
   Auditability's event log → Art.30/Art.5(2)).
2. **Evaluation Framework's `faithfulness` metric now genuinely uses
   `deepeval`.** The original build assumed DeepEval was too
   dependency-heavy for this platform's offline-testable module pattern
   and reimplemented it as a term-overlap heuristic instead — that
   assumption was never verified and was wrong (DeepEval installs in
   seconds, no torch, no local models). `core/deepeval_adapter.py` now
   wraps the real `deepeval.metrics.FaithfulnessMetric`, routed through
   this platform's LLM Gateway via a small `DeepEvalBaseLLM` adapter, with
   the original heuristic kept only as an automatic fallback.
3. **Distributed tracing didn't actually connect across modules.**
   Every module already exported real OTel spans, but no module
   propagated trace context on its *outbound* HTTP calls — so a request
   touching five modules produced five separately-rooted traces, not one.
   Every module's `main.py` now also instruments its httpx clients
   (`HTTPXClientInstrumentor().instrument()`), which injects the standard
   W3C `traceparent` header FastAPI already knows how to extract on the
   receiving end. Verified with an isolated reproduction (an
   `InMemorySpanExporter` capturing a caller span, an httpx client span
   and a downstream FastAPI server span, all sharing one `trace_id`), not
   just installed and assumed to work.

## Modules

### Module 1: Workflow Engine

Executes agent workflows as DAGs/graphs with neurosymbolic step routing,
confidence-gated autonomy, and human-in-the-loop checkpoints — the
orchestration core the rest of the platform's modules plug into. Design doc:
[`docs/module-01-workflow-engine-lld.md`](docs/module-01-workflow-engine-lld.md).
Build: [`modules/workflow-engine`](modules/workflow-engine).

### Module 2: Conversational Engine

Multi-turn dialogue management: persona control, channel adaptation
(web/WhatsApp/voice), streaming responses, and emotional/urgency-aware
handoff to a human. Design doc:
[`docs/module-02-conversational-engine.md`](docs/module-02-conversational-engine.md).
Build: [`modules/conversational-engine`](modules/conversational-engine).

### Module 3: LLM Gateway

The only module permitted to call model providers directly — quality-aware
routing, semantic caching, cost governance and failover across 20+
providers, behind an OpenAI-compatible API. Design doc:
[`docs/module-03-llm-gateway.md`](docs/module-03-llm-gateway.md).
Build: [`modules/llm-gateway`](modules/llm-gateway).

### Module 4: Tool Orchestration

The single point through which every agent action against an external tool
passes: MCP-based discovery and invocation, retries, circuit-breaking,
reliability-scored routing, and guarded just-in-time tool synthesis. Design
doc: [`docs/module-04-tool-orchestration.md`](docs/module-04-tool-orchestration.md).
Build: [`modules/tool-orchestration`](modules/tool-orchestration).

### Module 5: Intent Detection

The first classification step in most conversational and workflow paths:
classifies input into intents, decomposes compositional multi-goal
utterances into an LLM Gateway fallback, and monitors intent drift via
Population Stability Index. Design doc:
[`docs/module-05-intent-detection.md`](docs/module-05-intent-detection.md).
Build: [`modules/intent-detection`](modules/intent-detection).

### Module 6: Agentic RAG

Multi-hop, self-correcting retrieval: fans out to Vector DB/Graph DB/
Knowledge Base and fuses results, critiques its own groundedness, and
reformulates the query and re-retrieves when insufficient — before ever
reaching the LLM for the real answer. Design doc:
[`docs/module-06-agentic-rag.md`](docs/module-06-agentic-rag.md).
Build: [`modules/agentic-rag`](modules/agentic-rag).

### Module 7: Context Engineering

The final assembly step before a prompt goes to LLM Gateway: filters
candidate context through a domain ontology, ranks it by explainable
feature-weighted priority, and fits it into a token budget — summarising
high-priority overflow rather than dropping it outright. Design doc:
[`docs/module-07-context-engineering.md`](docs/module-07-context-engineering.md).
Build: [`modules/context-engineering`](modules/context-engineering).

### Module 8: Data Source Plugins

Owns connectivity to external data systems — relational databases, SaaS
APIs, file stores, data warehouses — on the platform's behalf: normalises
whatever it pulls into a common schema, detects and auto-adapts to source
schema drift, and scores data quality at ingestion so downstream agents
can weigh a source's trustworthiness rather than treating every feed
equally. Design doc:
[`docs/module-08-data-source-plugins.md`](docs/module-08-data-source-plugins.md).
Build: [`modules/data-source-plugins`](modules/data-source-plugins).

### Module 9: Knowledge Base

The system of record for unstructured source-of-truth content: ingests,
chunks, versions and access-policy-tags documents, then hands chunks to
Vector DB and Graph DB so Agentic RAG has something to retrieve. Chunk-
level policy tags and staleness-driven re-ingestion triggers are its two
differentiators over document-only access control and silently-aging
source material. Design doc:
[`docs/module-09-knowledge-base.md`](docs/module-09-knowledge-base.md).
Build: [`modules/knowledge-base`](modules/knowledge-base).

### Module 10: Vector DB

Stores and retrieves embeddings for semantic search on behalf of
Knowledge Base and any other module needing vector similarity — hybrid
dense-plus-sparse retrieval fused in a single query, and automatic
zero-downtime re-embedding when a better embedding model becomes
available, both via a real Qdrant backend rather than a bolted-together
substitute. Design doc:
[`docs/module-10-vector-db.md`](docs/module-10-vector-db.md).
Build: [`modules/vector-db`](modules/vector-db).

### Module 11: Graph DB

Stores entities and their relationships for graph-based reasoning and
memory — temporal (valid-from/valid-to) edges so agents can reason about
"what was true when," and mandatory causal-vs-correlational-vs-structural
edge typing so no relationship is silently treated as more meaningful
than it actually is. Design doc:
[`docs/module-11-graph-db.md`](docs/module-11-graph-db.md).
Build: [`modules/graph-db`](modules/graph-db).

### Module 12: Short-Term Memory

The working memory for a single active session: a token-budgeted message
buffer that the Conversational Engine and Context Engineering draw on
when assembling a prompt. Salience-weighted retention keeps high-value
content (numbers, commitments, explicit "remember this" cues) verbatim
through overflow summarisation rather than dropping it just because it
aged out. Design doc:
[`docs/module-12-short-term-memory.md`](docs/module-12-short-term-memory.md).
Build: [`modules/short-term-memory`](modules/short-term-memory).

### Module 13: Long-Term Memory

The durable, cross-session memory store for facts, episodes, semantic
and procedural knowledge — consolidation and decay keep it from growing
unbounded, a self-reflection loop lets agents improve from corrected
interactions without retraining, and a cryptographically provable
right-to-erasure flow turns GDPR-style forgetting into an auditable,
on-demand action rather than a manual data-protection project. Design
doc: [`docs/module-13-long-term-memory.md`](docs/module-13-long-term-memory.md).
Build: [`modules/long-term-memory`](modules/long-term-memory).

### Module 14: Guardrails

The safety gate every input and output can be checked against: jailbreak
detection, PII detection-and-redaction, denied-topic and groundedness
policy checks, all driven by per-tenant policy profiles, plus a red-team
runner that fires adversarial prompts at a shadow profile and records any
bypass as an incident. A zero-config default profile means `/check` works
out of the box before any tenant has configured one. Design doc:
[`docs/module-14-guardrails.md`](docs/module-14-guardrails.md).
Build: [`modules/guardrails`](modules/guardrails).

### Module 15: Sentinel Agents

Watches every agent's behavior for statistical deviation from its own
baseline (Welford's online algorithm for numerically stable running
mean/variance, z-scored per event) and for swarm-level correlated
deviation across agents in a sliding time window — then autonomously
pauses, escalates to Human Oversight, or alerts, depending on severity
and configured autonomy. Its pause/terminate calls target Workflow
Engine's real, already-built instance-control endpoints rather than a
stub. Design doc:
[`docs/module-15-sentinel-agents.md`](docs/module-15-sentinel-agents.md).
Build: [`modules/sentinel-agents`](modules/sentinel-agents).

### Module 16: Human Oversight

The human-in-the-loop approval queue: request enqueueing, claim/decide
workflows, and an override capture path that logs the original agent
proposal against the human's corrected action with extra audit weight.
Slack/Teams/webhook notification delivery is genuinely functional (those
channels are just webhook POSTs under the hood), and the decision
callback for a Workflow-Engine-originated request calls that module's
real approval-callback endpoint rather than a placeholder. Design doc:
[`docs/module-16-human-oversight.md`](docs/module-16-human-oversight.md).
Build: [`modules/human-oversight`](modules/human-oversight).

### Module 17: Regulatory and Compliance

Maps a single, once-implemented control to the specific clauses it
satisfies across every regulatory framework a tenant has enabled (EU AI
Act, NIST AI RMF, ISO 42001, DORA, GDPR), and generates framework-formatted
evidence packs — real PDFs — on demand. A config-driven crosswalk table
makes the "living regulatory feed" claim real: a new framework or
delegated act is a data change, never a code change, and publishing a new
version deprecates rather than deletes prior mappings so an in-flight
audit cycle never sees its evidence trail shift shape. Design doc:
[`docs/module-17-regulatory-compliance.md`](docs/module-17-regulatory-compliance.md).
Build: [`modules/regulatory-compliance`](modules/regulatory-compliance).

### Module 18: Evaluation Framework

Scores agent outputs against faithfulness, coherence, tool-trace
correctness and domain-specific metrics, both as a CI/CD gate
(`agenteval run --gate`) before deployment and as continuous sampling
against live production traffic. `faithfulness` is backed by the real
`deepeval` package (`deepeval.metrics.FaithfulnessMetric`, routed through
LLM Gateway via a custom `DeepEvalBaseLLM` adapter) — an earlier version
of this module assumed DeepEval was too heavyweight for this platform's
build pattern and reimplemented it as a heuristic instead; that
assumption was wrong and is corrected. `coherence` and
`tool_trace_correctness` remain local heuristics (no equivalent
off-the-shelf DeepEval metric), falling back further to an LLM Gateway
LLM-as-judge call for any metric without a local implementation — the
same multiple-sources-behind-one-interface shape the LLD calls for.
Design doc: [`docs/module-18-evaluation-framework.md`](docs/module-18-evaluation-framework.md).
Build: [`modules/evaluation-framework`](modules/evaluation-framework).

### Module 19: Observability

The platform-wide sink for every trace, span, metric and log this
platform's other modules emit, differentiated by two features built on
top: a Reasoning-Trace Reconstructor that turns a raw trace tree into a
plain-language decision narrative via LLM Gateway, and a Cost Attribution
Joiner that reads LLM Gateway's real `gen_ai.usage.*`/`llm_gateway.cost`
span attributes to show spend alongside performance as one dataset.
Stores spans in its own Postgres table behind a simplified HTTP ingestion
endpoint rather than standing up a real Tempo/Mimir/Loki/Grafana stack —
see its README for why that's the one remaining deviation worth calling
out here, now that every module in this platform propagates W3C trace
context on its outbound calls (`HTTPXClientInstrumentor`), closing the
actual end-to-end distributed tracing gap raised in review.
Design doc: [`docs/module-19-observability.md`](docs/module-19-observability.md).
Build: [`modules/observability`](modules/observability).

### Module 20: Auditability

The platform's immutable, tamper-evident event log: every other module
appends its notable events here (`POST /v1/events`), each one hash-chained
to the previous entry per tenant so any break is detectable, with an
audit-pack export (PDF/JSON evidence bundle) and a natural-language query
endpoint (via LLM Gateway) over the log. A real Postgres concurrency bug
surfaced in this module's own integration tier — `SELECT ... FOR UPDATE`
on a not-yet-existing row provides no locking, so a tenant's first-ever
event could race under concurrent writers — fixed with a
`pg_advisory_xact_lock` taken before the read; see the module's own README
for the full writeup.
Design doc: [`docs/module-20-auditability.md`](docs/module-20-auditability.md).
Build: [`modules/auditability`](modules/auditability).

### Module 21: MCP

The platform's single, governed entry point for MCP (Model Context
Protocol) traffic: a registry of MCP servers (the "internal server
marketplace"), a per-tenant/per-tool access policy enforced deny-by-default
(no policy row for a tenant/server means zero access), and a JSON-RPC 2.0
proxy that checks that policy before forwarding a request to the real
backing server. Distinct from Tool Orchestration (Module 4)'s own
`HTTPMCPClientAdapter`: that's a direct, ungoverned call from one caller to
one already-known MCP server, while this module is the opposite
direction — where a server gets *registered* so any caller platform-wide
can discover and be governed calling it, with Tool Orchestration itself a
natural (optional) caller of this module once a tool is registered here.
Design doc: [`docs/module-21-mcp.md`](docs/module-21-mcp.md).
Build: [`modules/mcp`](modules/mcp).

### Module 22: A2A

The platform's standardised agent-to-agent delegation boundary: lets
this platform's own agents hand a task to another autonomous agent —
this platform's own or a genuinely external, cross-vendor one — and lets
external agents hand a task to this platform in return, both over the
A2A protocol. `DelegationService` (outbound) does a card-fetch handshake
against the target's `/.well-known/agent.json` and checks the requested
skill is actually advertised before sending; `InboundGateway` (inbound)
enforces a deny-by-default Access Policy Engine — the same shape as
MCP's own (Module 21), applied here to "per-skill, not just
per-caller" — before dispatching an accepted task into Workflow Engine
(Module 1) as the real execution engine. The skills this platform
advertises and the skills it accepts inbound are the same set by
construction: both are read from one `skill_definition_map` config
value, so there's no separate list either side could drift from.
Design doc: [`docs/module-22-a2a.md`](docs/module-22-a2a.md).
Build: [`modules/a2a`](modules/a2a).

### Module 23: Agent Cards

The platform's trust-scored discovery registry for Agent Cards: any
agent gets a published, machine-readable capability manifest here, and
any orchestrator platform-wide can search that registry by skill and get
results ranked by a genuine, cross-module trust signal — `GET
/agent-cards` sorts by `trust_score` descending, not registration order.
`TrustScoreCalculator` computes that score from two real peers,
Evaluation Framework (Module 18)'s own per-agent metric-score history
and Regulatory Compliance (Module 17)'s own per-tenant control-coverage
percentage, weighted and renormalized over whichever signal(s) actually
have data — a component with no data is excluded, never defaulted to a
fake neutral number, and a down peer degrades that one signal instead of
failing the whole computation. Distinct from A2A (Module 22)'s own card
handling: A2A publishes and consumes cards scoped to its own protocol
mechanics (this platform's one outbound card, one target's card cached
per delegation), while this module is the platform-wide, governed,
trust-scored catalogue a discovery *search* runs against — the same
registry/direct-call split already drawn between MCP (Module 21) and
Tool Orchestration (Module 4).
Design doc: [`docs/module-23-agent-cards.md`](docs/module-23-agent-cards.md).
Build: [`modules/agent-cards`](modules/agent-cards).

### Module 24: Agent Marketplace / Registry

The platform's internal catalogue of built agents: a team publishes a
listing referencing an existing Agent Card (Module 23), it goes through
an explicit governance approval (`pending_review → published`, or
`rejected` with a reason — any other transition is a `409`) before
appearing in search, and every genuine reuse by a different team is
tracked. Catalogue search sorts by `reuse_count` descending by default,
recomputed from the real usage-event log on every `record-usage` call
rather than just incremented, so the denormalized counter and the log
it's derived from can never drift apart — "prevents duplicate
agent-building across teams" as the literal search order, not just
prose. Card data itself is never owned here: `CatalogueSyncService`
snapshots it from Agent Cards' own `GET /agent-cards/{id}` and
wholesale-replaces the listing's copy, the same "always a replace,
never a merge" convention MCP's own Capability Sync Service already
established. External monetisation (`external_listing_enabled`) is a
real field with no billing logic behind it — a documented placeholder
for Module 33 (Billing and Metering) once it exists, not a half-built
feature.
Design doc: [`docs/module-24-agent-marketplace.md`](docs/module-24-agent-marketplace.md).
Build: [`modules/agent-marketplace`](modules/agent-marketplace).

### Module 25: LLMOps

The platform's model registry and staged-rollout controller: a new
model version is registered, deployed to a target at some canary
traffic percentage, and only promoted to `active` — automatically
superseding whatever was active before — once real evidence from
Evaluation Framework (Module 18)'s own `GET /scores` clears a
configurable bar (a minimum sample size, so a canary can't pass on a
timer or on volume alone, and a minimum pass rate). `promote` always
re-runs that gate rather than trusting an earlier pass, and any
transition outside the legal set (`canary → active`/`rolled_back`,
`active → rolled_back`/`superseded`) is a `409` — the same explicit
legal-transition-table shape Agent Marketplace (Module 24)'s own
governance workflow already established. Distinct from LLM Gateway
(Module 3): this module is the decision-and-record-keeping layer for
*which* model version should be active, not the request-routing layer
itself — actually wiring that decision into LLM Gateway's live routing
is real future work this LLD calls out explicitly rather than quietly
half-wiring it here.
Design doc: [`docs/module-25-llmops.md`](docs/module-25-llmops.md).
Build: [`modules/llmops`](modules/llmops).

## Running any module locally

```bash
cd modules/<module-name>
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed
docker compose -f deploy/docker-compose.yml up --build    # full stack (Postgres/Redis + dependency-stub)
```
