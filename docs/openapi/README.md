# OpenAPI specs — all 34 modules

Real, generated OpenAPI 3.1 specs, one per module — `app.openapi()` dumped
straight from each module's own FastAPI app, the exact same document that
module serves live at its own `GET /openapi.json` once running. Nothing here
is hand-written or guessed; regenerate any time the code changes:

```bash
./scripts/generate_openapi_specs.sh                    # every module
./scripts/generate_openapi_specs.sh multi-tenancy       # just one
```

`index.json` is a generated summary (module, port, title, endpoint count,
path list) — used by the API explorer artifact and a reasonable starting
point for scripting against the catalogue yourself.

## Every module is independently browsable, live

Any running module serves interactive docs with zero extra setup —
FastAPI's built-in Swagger UI and ReDoc:

```
http://localhost:<port>/docs        # Swagger UI, "try it out" included
http://localhost:<port>/redoc       # ReDoc, better for reading top to bottom
http://localhost:<port>/openapi.json
```

## The platform's own live aggregate: SDK and Developer Portal

You don't need this static snapshot to get the full catalogue once the
platform is actually deployed — **SDK and Developer Portal (Module 34)**
already does this for real, continuously: it polls every configured peer's
own live `GET /openapi.json` (through that peer's own `ServiceAuthMiddleware`,
so even fetching docs respects the platform's real security model) and
regenerates a minimal, working Python client per module whenever a spec's
content hash actually changes. This static `docs/openapi/` snapshot exists
for browsing the platform's shape without anything running; the live
aggregate in SDK and Developer Portal is the source of truth once deployed.

## Ports (all 34, sequential 8080–8113)

"Endpoints" below counts operations (a `GET` and `POST` on the same path
count as two) — 308 total across 282 distinct URL paths. `index.json`
carries both (`operation_count`, `path_count`) per module.

| Port | Module | Endpoints |
|---|---|---|
| 8080 | Workflow Engine | 12 |
| 8081 | Conversational Engine | 7 |
| 8082 | LLM Gateway | 8 |
| 8083 | Tool Orchestration | 7 |
| 8084 | Intent Detection | 6 |
| 8085 | Agentic RAG | 4 |
| 8086 | Context Engineering | 5 |
| 8087 | Data Source Plugins | 8 |
| 8088 | Knowledge Base | 7 |
| 8089 | Vector DB | 7 |
| 8090 | Graph DB | 6 |
| 8091 | Short-Term Memory | 5 |
| 8092 | Long-Term Memory | 9 |
| 8093 | Guardrails | 6 |
| 8094 | Sentinel Agents | 7 |
| 8095 | Human Oversight | 7 |
| 8096 | Regulatory and Compliance | 9 |
| 8097 | Evaluation Framework | 7 |
| 8098 | Observability | 6 |
| 8099 | Auditability | 8 |
| 8100 | MCP | 8 |
| 8101 | A2A | 9 |
| 8102 | Agent Cards | 7 |
| 8103 | Agent Marketplace | 11 |
| 8104 | LLMOps | 11 |
| 8105 | FinOps | 8 |
| 8106 | Deployment Strategy | 9 |
| 8107 | Multi-modality | 5 |
| 8108 | PromptOps | 12 |
| 8109 | Multi-tenancy | 39 |
| 8110 | Identity and Access | 12 |
| 8111 | Secrets and Credential Management | 11 |
| 8112 | Billing and Metering | 10 |
| 8113 | SDK and Developer Portal | 15 |

Every module also serves `/healthz` and `/metrics` — infra endpoints,
not counted above since they're outside the module's own tagged API
surface (see each spec for the exact set FastAPI documents).

## Browsing the catalogue

[`docs/openapi/`](.) itself is just JSON — for browsing, use the
**Tectonic API Explorer** artifact (a searchable, categorized UI over
all 308 operations, with request/response schemas and a generated curl
example per endpoint), or any running module's own `/docs`/`/redoc`.
