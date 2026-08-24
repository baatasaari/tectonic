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
| 20–34 | Not yet started |

Each module is designed, built and tested independently (its own repo-style
subtree under `modules/`, own README, own CI-shaped test tiers), then
integrated. See a module's low-level design doc under `docs/` before
building against it.

## Enterprise-readiness hardening

A dedicated review pass across all 19 built modules — gaps, technical
depth, edge cases, and custom code that open-source frameworks could
replace — is landing as a series of independent, foundational-risk-first
branches/PRs, each scoped to one concern so it can be reviewed and merged
on its own:

| # | Branch | Scope | Status |
|---|---|---|---|
| 1 | `claude/resiliency-retries` | Retries + circuit breakers on every outbound HTTP call | Built — merged |
| 2 | `claude/postgres-integration-tests` | Repository layer tested against a real Postgres, not just SQLite | Built — merged |
| 3 | `claude/durable-background-jobs` | Module 17's evidence-pack generation surviving a pod restart | Built — merged |
| 4 | `claude/pooling-and-pagination` | Connection pooling tuned to Helm replica counts + pagination on list endpoints | Built — merged |
| 5 | `claude/ci-cd-pipeline` | Lint + test gating via GitHub Actions | Built (this branch) |
| 6 | JWT bearer auth | Shared-signing-key service-to-service auth (final, dedicated push) | Built — separate PR |

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

**Branch 6** (JWT bearer auth) is built and merging in this same
sequence; see its own PR for details until this section is updated with
its narrative too.

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

## Running any module locally

```bash
cd modules/<module-name>
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed
docker compose -f deploy/docker-compose.yml up --build    # full stack (Postgres/Redis + dependency-stub)
```
