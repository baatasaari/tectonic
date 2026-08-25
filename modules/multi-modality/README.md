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
  security/                 Service-to-service JWT bearer auth (shared signing key)
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
