# Multi-modality — Module 28

The platform's unified multi-modal ingestion and governance layer: raw
media of any of four modalities (text, voice, image, document) is
normalized into a common `extracted_content` shape by a pluggable,
per-modality pipeline, then optionally checked for groundedness against
a supplied reference via Guardrails (Module 14)'s own real check
endpoint before being handed back to the caller. Full design doc:
[`../../docs/module-28-multi-modality.md`](../../docs/module-28-multi-modality.md).

## Layout

```
src/multi_modality/
  main.py                 FastAPI app, lifespan wiring, /healthz, /metrics
  app_context.py           Process-wide dependency container
  config.py                  Pydantic Settings — LLD config schema
  core/
    domain.py                 ExtractionRecord dataclass, Modality/GroundednessDecision enums
    ports.py                    Repository, ModalityExtractor protocol, Guardrails client
    extractors.py                 Per-modality extractors (text/voice/image/document stand-ins)
    fakes.py                       In-memory implementations of every port, for unit tests
    extraction_service.py           Extraction Service — runs the right extractor + the groundedness gate
  db/                      SQLAlchemy 2.0 async models + repository (Extraction)
  clients/                 Resilient HTTP client to Guardrails
  security/                 Service-to-service JWT bearer auth (shared signing key), the entitlement gate, real OpenAPI security scheme declarations
  telemetry/                OTel tracing, Prometheus metrics, structlog logging
  api/                       FastAPI router — extract, list, get
  schemas/                    Pydantic request/response models
```

## Design notes vs. the LLD

- **One unified interface across four modalities.** `POST
  /v1/multi-modality/extractions` takes a `modality` field and returns
  the identical `ExtractionSchema` shape regardless of which pipeline
  ran.
- **A real cross-modal groundedness gate, not a claimed one.** When a
  `grounding_context` is supplied, the extracted content is checked
  against it through Guardrails' own real `POST /v1/guardrails/check`
  (`stage=output`) — the identical endpoint and `groundedness_check`
  logic this platform already uses to catch ungrounded LLM output. The
  same "real peer, not invented" convention this platform already
  established for Agent Cards' trust score and Deployment Strategy's
  canary health.
- **A down Guardrails peer degrades to `unavailable`, not a crashed
  extraction.** `ExtractionService._safe_call` wraps the groundedness
  check independently of the extraction itself: the caller still gets
  their extracted content back, tagged `groundedness_decision
  =unavailable` rather than losing the whole request.
- **Honest about what "accuracy" means without a real ASR/vision
  provider wired.** `core/extractors.py`'s `VoiceExtractor`/
  `ImageExtractor`/`DocumentExtractor` are documented, swappable
  stand-ins (`core/ports.py`'s `ModalityExtractor` protocol) for a real
  cloud Speech-to-Text/Vision/OCR API — wiring one is real, valuable
  future work this LLD calls out explicitly, the same "documented
  placeholder, not a half-built feature" posture Agent Marketplace and
  LLMOps already take.

- **Enforces its own subscription entitlement via `EntitlementGateMiddleware`**
  (`security/entitlement_gate.py`) — see Agent Cards' README and the rollout
  playbook doc (`docs/entitlement-gate-rollout.md`) for the shared reference
  implementation. Layered after `ServiceAuthMiddleware` (authenticate, then
  entitle), it calls Multi-tenancy's real `GET /tenants/{id}/gate?module=multi-modality`,
  denying with `402 Payment Required` when the tenant's subscription doesn't
  include this module. It **fails open** if Multi-tenancy is unreachable — a
  deliberate contrast with `ServiceAuthMiddleware`'s zero-trust fail-closed
  posture.

- **Its generated OpenAPI document declares the real auth it enforces**
  (`security/openapi_security.py`) — see Workflow Engine's README and the
  independent architecture assessment's §3.6 for the shared reference
  implementation and full reasoning. `ServiceAuthMiddleware` is plain
  Starlette middleware, invisible to FastAPI's automatic OpenAPI
  generation, so this module's spec previously declared no
  `securitySchemes` at all; `configure_openapi_security` fixes that,
  reusing `jwt_auth.py`'s own `_EXCLUDED_PATHS` as the one source of
  truth for which paths are genuinely unauthenticated.

- **Kubernetes hardening** (`deploy/helm/`; independent architecture
  assessment §3.7) — see Workflow Engine's README for the full reasoning
  and reference implementation. A dedicated ServiceAccount with no
  auto-mounted API token (this module never calls the Kubernetes API);
  pod/container `securityContext` (non-root, read-only root filesystem
  with a small `/tmp` `emptyDir`, all capabilities dropped, a seccomp
  profile); a `NetworkPolicy` restricting ingress to this module's own
  namespace; separate startup/liveness/readiness probe semantics instead
  of two identical probes; and `topologySpreadConstraints` across nodes.

- **NUL bytes/invalid enum values reaching the database or crashing
  unhandled** (ticket #82's platform-wide sweep, following the same bug
  a real CI run found on Multi-tenancy's and Billing and Metering's own
  contract tiers — see either module's own README for the original
  finding). `GET /extractions`'s `tenant_id` never ran through a
  NUL-byte validator; fixed with `_reject_null_byte_query()`. That same
  route's own `modality` was a bare `str` hand-converted to `Modality`,
  raising an unhandled `ValueError` (500) for any non-member string —
  now typed `Modality` directly so FastAPI/Pydantic itself rejects an
  invalid value with a clean 422.

- **The platform's own "unbounded offset" class** (this repo's own
  `CLAUDE.md`-documented recurring bug — already fixed for Billing and
  Metering's, LLM Gateway's, Multi-tenancy's and Workflow Engine's own
  `offset` query params; found again, still open here, when Evaluation
  Framework's own new contract-test tier hit the identical gap and a
  platform-wide grep confirmed it recurred everywhere else that hadn't
  already fixed it). `GET /extractions`'s `offset` had no upper bound, so a
  value past Postgres's `bigint` range (`> 9223372036854775807`) crashed
  with an unhandled `asyncpg.DataError` instead of a clean `422`. Fixed
  with the identical `le=1_000_000_000` bound those four modules already
  use — comfortably past any real pagination need, comfortably under the
  overflow. Mechanical, not contract-tier-discovered here (this module
  has no contract tier of its own yet) — found by the platform-wide grep
  instead.

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
