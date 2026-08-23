# LLM Gateway — Module 3

The only module permitted to call model providers directly. Every other
module that needs LLM inference goes through this gateway — never a
provider SDK directly — which is what makes provider swaps, cost governance
and quality routing possible platform-wide. Full design doc:
[`../../docs/module-03-llm-gateway.md`](../../docs/module-03-llm-gateway.md).

## Layout

```
src/llm_gateway/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                 Pydantic Settings — LLD config schema
  core/
    domain.py                VirtualKey/BudgetPolicy/RequestLog/ProviderConfig dataclasses
    ports.py                   Repository, cache, quality-score feed, provider client, secrets
    fakes.py                    In-memory implementations of every port, for unit tests
    normalizer.py                 Request Normalizer
    similarity.py                  Shared term-frequency cosine similarity for the cache
    semantic_cache.py               Semantic Cache — in-memory (tests) and Redis (prod) impls
    router.py                        Quality-Aware Router
    cost_governance.py                Cost Governance Engine
    failover.py                        Failover Manager
    gateway_service.py                  The request orchestrator (this module's "scheduler")
    deprecation_watcher.py               Model Deprecation Watcher
  db/                      SQLAlchemy 2.0 async models + repository
  clients/                 HTTP provider adapter, Redis quality-score store, Secrets client
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI routers — OpenAI-compatible completions/embeddings, admin
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **Resiliency.** Every outbound HTTP call this module makes to a peer module goes through `ResilientHTTPClient` (`clients/resilience.py`): exponential-backoff retry on network errors and 5xx responses (never 4xx — a client error means the peer already processed the request and rejected it, so retrying just repeats the mistake), and a circuit breaker (`aiobreaker`) that opens after repeated failures so a struggling peer gets a break instead of a retry storm, and this module fails fast instead of piling up requests against a peer that's already down.

- **Provider adapter.** The LLD names LiteLLM as the provider abstraction.
  `clients/http_provider_client.py` implements `ProviderClient` as a generic
  OpenAI-compatible HTTP adapter instead of importing the `litellm` package
  directly: every `ProviderConfig.endpoint` already models a per-provider
  base URL, and OpenAI-compatible `/chat/completions` is what the large
  majority of providers and proxies speak today — including LiteLLM's own
  proxy mode, so pointing a `ProviderConfig` at a running LiteLLM proxy is a
  drop-in way to get its 100+-provider coverage. Swapping in the `litellm`
  Python SDK directly means implementing the same `ProviderClient` Protocol
  against `litellm.acompletion` — same boundary Module 1 draws around ADK.
- **Semantic cache.** RedisVL (real embeddings + ANN search) is the LLD's
  production choice; `core/similarity.py` implements a lightweight local
  term-frequency cosine similarity instead, so caching works without a
  network round-trip to an embedding model on every lookup. Staleness
  awareness is a `stale` flag per entry a drift-detection signal can set
  (`flag_stale`/`invalidate_stale`), rather than a fixed TTL.
- **Quality-aware router.** Cost and latency aren't separately tracked
  fields in the LLD's `ProviderConfig` data model, so the router uses each
  provider's `priority` as a shared proxy for both, blended with the live
  quality score from the (stubbed, until Module built) Evaluation
  Framework feed per the configured strategy weights.
- **Cost governance.** Implements optimistic reserve-then-settle: an
  estimated ceiling is reserved against the budget before the provider call
  (so two concurrent requests can't both slip under a limit that only one
  should), then settled to the real cost once the provider responds.

## Running locally

```bash
uv venv && uv pip install -e ".[dev]"
pytest                                                    # unit tests, no external services needed

docker compose -f deploy/docker-compose.yml up --build    # full stack incl. Postgres, Redis, dependency-stub
```
