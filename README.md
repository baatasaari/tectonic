# Tectonic — Agentic AI Platform

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
| 17–34 | Not yet started |

Each module is designed, built and tested independently (its own repo-style
subtree under `modules/`, own README, own CI-shaped test tiers), then
integrated. See a module's low-level design doc under `docs/` before
building against it.

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

## Running any module locally

```bash
cd modules/<module-name>
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed
docker compose -f deploy/docker-compose.yml up --build    # full stack (Postgres/Redis + dependency-stub)
```
