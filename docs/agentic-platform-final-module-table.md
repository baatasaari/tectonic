# Cloud Agnostic Agentic AI Platform — Final Module Table

All 34 modules with description, inputs, outputs, commercial value, implementation approach and key metrics. Processing time targets from the earlier spec still apply per module; this table adds the "why it sells" and "how it gets built" dimensions.

## Orchestration and Runtime

| Module | Description | Inputs | Outputs | Value | Implementation Approach | Key Metrics |
|---|---|---|---|---|---|---|
| Workflow Engine | Executes agent workflows as DAGs/graphs with drag-and-drop authoring, neurosymbolic step routing and confidence-gated autonomy | Workflow definition, trigger event, runtime context | Execution trace, step outputs, human-approval requests | Lets non-technical teams build and change workflows without engineering, while regulated steps stay deterministic; core reason a customer buys the platform over stitching frameworks together | Graph execution engine (e.g. LangGraph-style state machine or custom), symbolic rule layer for deterministic steps, visual builder as separate frontend consuming the same workflow schema | Steps/sec, workflow success rate, human-approval wait time |
| Conversational Engine | Multi-turn dialogue management with persona, channel adaptation, emotional/urgency-aware routing | User utterance, session ID, channel, history | Response, updated state, handoff signal | Consistent conversational quality across channels without rebuilding logic per channel | State machine per session, streaming response pipeline, channel adapters (web, voice, WhatsApp) as pluggable modules | Turn completion rate, handoff rate, session length |
| LLM Gateway | Single entry point routing to 20+ providers with failover, quality-aware routing, semantic caching | Model request, budget context | Model response, provider used, cost, cache flag | Removes vendor lock-in and gives cost control immediately visible to finance stakeholders | Reverse proxy layer (Go/Rust for low overhead), OpenAI-compatible API, pluggable provider adapters, cache layer with staleness detection | Requests/sec, cache hit rate, cost per request, provider availability |
| Tool Orchestration | Discovery, invocation, retry and reliability-scored routing for external tools | Tool call request, agent context | Tool result, retry status, execution metadata | Reduces agent failure from flaky third-party tools without manual intervention | Tool registry with health scoring, circuit breaker pattern, MCP-compatible tool interface | Tool success rate, retries per call, latency by tool |

## Intelligence Layer

| Module | Description | Inputs | Outputs | Value | Implementation Approach | Key Metrics |
|---|---|---|---|---|---|---|
| Intent Detection | Classifies input into intents, handles compositional multi-goal utterances, monitors intent drift | Raw input, context, taxonomy | Intent label, confidence, fallback flag | Correct routing from the first message, fewer failed conversations | Fine-tuned small classifier or LLM-based classification with confidence calibration, drift monitoring dashboard | Classification accuracy, false-positive rate, drift alerts |
| Agentic RAG | Multi-hop, self-correcting retrieval with hybrid symbolic-vector lookup and provenance chains | Query, retrieval context, source corpus | Retrieved passages, groundedness score, synthesized context | Materially lower hallucination rate than standard RAG, provable to customers via groundedness metrics | Retrieval-critique-reformulate loop, hybrid retriever (vector plus symbolic rule lookup for structured facts), citation tracking through pipeline | Retrieval precision/recall, groundedness score, hop count |
| Context Engineering | Assembles, compresses, prunes context within token budget using ontology constraints | Candidate context, token budget, task type | Assembled context, tokens used | Cheaper, more accurate model calls since irrelevant context never reaches the LLM | Ontology-tagged context store, learned prioritisation based on eval feedback, token budget enforcement | Token utilisation, truncation rate, quality delta |

## Data Layer

| Module | Description | Inputs | Outputs | Value | Implementation Approach | Key Metrics |
|---|---|---|---|---|---|---|
| Data Source Plugins | Pre-built connectors with schema drift auto-adaptation and data quality scoring | Connector config, credentials, query | Normalised data, sync status | Fast time-to-value for customers with existing systems, no bespoke integration project per source | Plugin architecture per source type, schema diffing on each sync, quality scoring pipeline | Sync success rate, freshness lag, drift incidents |
| Knowledge Base / Document Management | Ingests, chunks, versions and manages source-of-truth documents feeding Agentic RAG | Raw documents, metadata, access policy | Chunked/indexed content, version history | Gives customers control over what agents "know" and when, essential for regulated content accuracy | Document pipeline (parse, chunk, embed), version control with diffing, access-policy tagging at chunk level | Ingestion throughput, chunk quality score, staleness rate |
| Vector DB | Hybrid dense-sparse-graph embedding storage with automatic model migration | Text/embeddings, query, filters | Ranked results with scores | Single query surface instead of stitching three separate systems together | ANN index (HNSW or similar) plus keyword index plus lightweight graph layer, background re-index on model upgrade | Query latency p50/p95/p99, recall@k |
| Graph DB | Temporal, causally-typed entity/relationship storage | Node/edge writes, graph query | Query result (nodes, edges, paths) | Supports reasoning that pure vector search cannot ("what changed and why"), valuable for audit and long-term memory | Property graph store with temporal versioning on edges, causal-vs-correlation edge typing convention | Query latency, traversal depth, write throughput |

## Memory

| Module | Description | Inputs | Outputs | Value | Implementation Approach | Key Metrics |
|---|---|---|---|---|---|---|
| Short-Term Memory | Token-budgeted session buffer with salience-weighted retention | Message, session ID, token budget | Buffer state, summary | Keeps conversations coherent without ballooning cost | FIFO buffer with salience scoring model deciding what survives summarisation | Overflow rate, summarisation frequency |
| Long-Term Memory | Hybrid store with self-reflection loop, governed cross-agent sharing, verifiable forgetting | Memory item, scope, query | Stored confirmation, ranked retrievals | Agents that genuinely improve and personalise over time, and provably forget on request, a compliance and UX win at once | Hybrid store (Postgres for facts/episodic, vector store for semantic), reflection log per agent, policy-gated cross-agent read access, cryptographic deletion proof | Recall accuracy, consolidation frequency, forgetting compliance rate |

## Governance and Safety

| Module | Description | Inputs | Outputs | Value | Implementation Approach | Key Metrics |
|---|---|---|---|---|---|---|
| Guardrails | Input/output validation with OWASP Agentic Top 10 coverage and continuous self-testing | Input/output text, policy profile | Allow/block/redact decision | The baseline trust requirement for any regulated customer, sellable as "we test ourselves continuously" | Gateway-layer policy enforcement, integrated third-party detectors plus custom rules, scheduled red-team agent runs | Intervention rate, false-positive/negative rate |
| Sentinel Agents | Runtime agents monitoring other agents, with per-agent behavioural baselining and swarm-level anomaly detection | Agent action stream, policy rules | Alert, autonomous intervention, audit event | Genuinely underserved area; catches problems no single-agent monitor would see | Streaming anomaly detection per agent baseline, cross-agent correlation layer for swarm-level signals | Detection rate, false-alarm rate, mean time to detect |
| Human Oversight | Designed-in approval queues, override logging, escalation routing per EU AI Act Article 14 | Escalation trigger, decision context | Approval/rejection, override record | Turns a legal requirement into a built-in feature rather than a customer afterthought | Queue and routing service tied into Workflow Engine's confidence-gated steps, immutable override log feeding Auditability | Approval turnaround time, override rate |
| Regulatory and Compliance | Crosswalk engine mapping controls once to EU AI Act, NIST AI RMF, ISO 42001, DORA, with living regulatory feed | Control implementation event, active framework profiles | Framework-specific evidence records | Turns compliance from cost centre into procurement-winning feature | Config-driven mapping tables per framework, evidence generator pulling from Auditability, versioned regulatory profile updates | Framework coverage %, evidence completeness |

## Quality and Trust

| Module | Description | Inputs | Outputs | Value | Implementation Approach | Key Metrics |
|---|---|---|---|---|---|---|
| Evaluation Framework | Faithfulness, coherence, tool-trace scoring, continuous production evaluation | Agent output, reference data, metric set | Scores, pass/fail gate | Objective quality evidence for both engineering and compliance conversations | Eval harness wrapping multiple libraries (as in AgentEval), sampled production traffic evaluation feeding back into routing | Score distributions, gate pass rate |
| Observability | OpenTelemetry GenAI-compliant tracing with reasoning-trace visualisation and cost-attributed tracing | Span/trace/metric data | Queryable traces, dashboards, alerts | Debugging time for agent failures drops from hours to minutes | OTel GenAI semantic convention instrumentation, trace store, narrative reconstruction layer over raw spans | Trace completeness, ingestion latency |
| Auditability | Immutable chained logs with cryptographic tamper-evidence and natural-language audit query | System/agent events, decision context | Log entry, audit pack, provenance chain | The evidence layer every other governance module depends on; a genuine sales differentiator for regulated buyers | Append-only hash-chained log store, audit pack generator per framework, LLM-based query layer over trace data | Integrity verification rate, pack generation time |

## Interoperability

| Module | Description | Inputs | Outputs | Value | Implementation Approach | Key Metrics |
|---|---|---|---|---|---|---|
| MCP | Standardised agent-to-tool/data interface over JSON-RPC, with internal server marketplace | MCP client request | MCP server response | Avoids bespoke integration per tool, and lets customers govern their own internal tool catalogue | MCP server/client SDK implementation, internal registry with access policy per server | Uptime, request success rate |
| A2A | Standardised agent-to-agent delegation and capability negotiation, cross-vendor federation | A2A task request, target agent card | Task result, delegation status | Genuine future-proofing story: agents interoperate with third-party ecosystems, not locked to this platform alone | A2A protocol SDK, agent card publishing/consumption, negotiation handshake logic | Delegation success rate, cross-vendor compatibility |
| Agent Cards | Machine-readable, trust-scored capability manifests for discovery | Agent registration, capability definition | Published card, discovery response | Lets orchestrators choose the best agent for a task, not just the first one found | JSON schema per A2A spec, trust score computed from historical performance and compliance posture | Card freshness, discovery success rate |
| Agent Marketplace / Registry | Internal catalogue of built agents with governance, reuse and (future) external monetisation | Agent metadata, usage policy | Searchable catalogue, reuse metrics | Prevents duplicate agent-building across teams, and opens a future revenue channel if opened externally | Catalogue service on top of Agent Cards, governance workflow for publishing, usage analytics | Reuse rate, catalogue growth, external listing revenue (if enabled) |

## Operations

| Module | Description | Inputs | Outputs | Value | Implementation Approach | Key Metrics |
|---|---|---|---|---|---|---|
| LLMOps | Model registry, versioning, staged rollout, automatic canary evaluation | Model artefact/config, deployment target | Deployment status, active version | Safe model upgrades without manual sign-off bottlenecks | Model registry, canary rollout pipeline gated by Evaluation Framework scores | Rollout success rate, rollback frequency |
| FinOps | Budgets, chargeback, autonomous cost-optimisation agent, predictive forecasting | Usage events, budget policy | Cost reports, budget alerts | Directly answers the CFO question "what will this cost us," and actively reduces spend, not just reports it | Usage aggregation pipeline, policy engine, autonomous tuning agent operating within bounded limits | Budget adherence, cost per tenant, forecast accuracy |
| Deployment Strategy | Cloud-agnostic packaging with agent-aware canary analysis | Build artefact, rollout policy | Deployment status, canary health | Deploys safely across any cloud without vendor rewrite, with agent-specific health signals not just infra ones | Containerised packaging (Kubernetes-based), canary analysis watching groundedness/guardrail/cost signals as promotion gates | Deployment frequency, change failure rate, MTTR |

## Modality

| Module | Description | Inputs | Outputs | Value | Implementation Approach | Key Metrics |
|---|---|---|---|---|---|---|
| Multi-modality | Text, voice, image, document handling with cross-modal groundedness checks | Raw media | Extracted/generated content | Widens use cases (voice banking, document-heavy claims) without separate product lines | Modality-specific pipelines (ASR, vision model, document parser) unified behind one interface, groundedness check applied post-extraction | Transcription/extraction accuracy, conversion latency |

## Foundations

| Module | Description | Inputs | Outputs | Value | Implementation Approach | Key Metrics |
|---|---|---|---|---|---|---|
| PromptOps | Prompt versioning, A/B testing, automated reflection-based optimisation | Prompt draft, test suite | Deployed version, test results | Prompts improve over time with far less manual tuning effort | Prompt registry with CI/CD gating, reflection-based optimiser (GEPA-style) running against Evaluation Framework | Version count, drift incidents, A/B significance rate |
| Multi-tenancy | Data, config and usage isolation per tenant across all modules | Tenant context | Isolation enforcement result | Non-negotiable for a multi-customer SaaS platform; sells trust | Tenant-scoped data partitioning at the storage layer, request-level tenant context propagation | Isolation breach incidents (target zero) |
| Identity and Access | Authentication and role/scope-based access control, zero-trust agent identity | Credential/token, requested action | Auth decision, scoped token | Every agent and user individually accountable, not just a shared service account | OAuth2/OIDC for users, per-agent identity issuance and scoped tokens for agent-to-agent calls | Auth success rate, unauthorised attempts blocked |
| Secrets and Credential Management | Vaulting, rotation and per-tenant isolation of third-party API keys and credentials | Secret to store, rotation policy | Retrieved secret (scoped), rotation confirmation | Removes a common production security failure mode (hardcoded/shared keys) | Integration with a secrets manager (Vault-style), per-tenant key namespaces, automatic rotation scheduling | Rotation compliance rate, secret access audit completeness |
| Billing and Metering | Usage metering per module/tenant feeding subscription billing | Usage event, pricing plan | Metered usage record, invoice line | Makes the module-based subscription model real and defensible, not aspirational packaging | Event-driven metering pipeline per module, plan/pricing engine, invoice generation | Metering accuracy, billing dispute rate |
| SDK and Developer Portal | Client SDKs, API documentation, sandbox environment for customer developers | Developer account, API usage | SDK packages, documentation, sandbox access | The actual driver of adoption; without this every integration is a bespoke project, which kills the subscription model | Language-specific SDKs generated from OpenAPI spec, interactive docs, sandboxed tenant for trial/dev use | SDK adoption rate, time-to-first-successful-call, support ticket volume |

## How to read the Value column

Value is written as the reason a buyer or user cares, not a restatement of the feature. This is deliberate: several modules (Auditability, Regulatory and Compliance, FinOps) exist mainly because they are what turns a technically impressive platform into one that finance, risk and procurement teams will actually sign off on, which is where most competing platforms lose deals.
