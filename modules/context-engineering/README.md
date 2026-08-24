# Context Engineering — Module 7

The final assembly step before a prompt goes to LLM Gateway: takes
candidate context (from Agentic RAG, Short-Term Memory, Long-Term Memory,
Workflow context) and shapes it into the actual prompt context within a
token budget, prioritising what matters most for the specific task. Does
not retrieve content itself — consumes retrieved candidates and decides
what survives into the final prompt. Full design doc:
[`../../docs/module-07-context-engineering.md`](../../docs/module-07-context-engineering.md).

## Layout

```
src/context_engineering/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                CandidateItem/TaggedItem/RankedItem/AssembledItem dataclasses
    ports.py                   Repository, LLM Gateway (summarisation), Evaluation Framework feedback
    fakes.py                    In-memory implementations of every port, for unit tests
    tokenization.py               Token counting — whitespace-based estimate, no tiktoken network fetch
    ontology_filter.py             Ontology Filter — tags + excludes ungoverned policy tags
    prioritisation_engine.py        Prioritisation Engine — feature-weighted, explainable scoring
    token_budget_enforcer.py         Token Budget Enforcer — greedy knapsack selection
    compression.py                    Compression/Summarisation — LLM Gateway call, used sparingly
    context_assembly_service.py        The assembly orchestrator (this module's "scheduler")
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP clients for LLM Gateway and the Evaluation Framework feedback feed
  security/                 Service-to-service JWT bearer auth (shared signing key)
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI routers — assemble, ontologies, weights
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Tokenisation.** The LLD names `tiktoken`. `core/tokenization.py`
  implements a whitespace/word-count-based estimator instead —
  `tiktoken`'s encodings are fetched from a remote blob store on first use
  and cached, a network dependency this module's tests shouldn't carry.
  Close enough for budget *enforcement* (this module's actual job); swap in
  `tiktoken` — or the model-specific tokenizer LLM Gateway's routing
  decision implies — by implementing the same `TokenCounter` interface.
- **Prioritisation Engine.** Feature-weighted scoring over a small,
  explainable feature set (role match, entity-type match, policy-tag match
  count, source identity) rather than a full ML pipeline, per the LLD's own
  stated rationale: "keeps this explainable and tunable rather than an
  opaque black box." `update_from_feedback` nudges weights by a bounded
  step per Evaluation Framework signal rather than overwriting them
  outright.
- **Ontology Filter as a real filter, not just tags.** An item whose
  metadata declares a `policy_tags` entry the tenant's ontology doesn't
  recognise is excluded outright, not merely left untagged — ungoverned
  content shouldn't silently reach the prompt.
- **Service-to-service JWT auth.** Before this, no module authenticated
  any of its inbound HTTP calls — any process able to reach a module's
  port could call it, and every outbound call this module makes carried
  no credential at all. `security/jwt_auth.py` adds shared-signing-key
  (HS256) bearer auth: `ServiceAuthMiddleware` verifies every inbound
  request's `Authorization: Bearer <JWT>` against this module's own
  `service_name` as the required audience (except `/healthz` and
  `/metrics` — Kubernetes probes and Prometheus scraping carry no auth
  token); `ServiceBearerAuth` (an `httpx.Auth` flow) mints a fresh,
  short-lived (5 min default) token scoped via the `aud` claim to the
  *specific* peer being called on every outbound request each of
  `HTTPLLMGatewayClient` and `HTTPEvaluationFeedbackClient` makes — a
  token minted to call one peer is rejected if replayed against a
  different one. The shared secret (`TECTONIC_JWT_SHARED_SECRET`, one
  Kubernetes Secret referenced by every module's Helm chart under this
  same literal env var name, not a per-module-prefixed one) defaults to
  an obviously-insecure placeholder for zero-config local dev/tests;
  `main.py` logs a startup warning if it's still active. This is
  service-to-service auth for inter-module calls, not the platform's
  external-facing user-auth story — a real API gateway/OAuth layer in
  front of the platform's own entry points is a separate, larger
  concern, out of scope here.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, dependency-stub
```
