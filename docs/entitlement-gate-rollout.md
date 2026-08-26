# Entitlement gate rollout playbook

How the platform enforces its subscription model at the request path:
Multi-tenancy (Module 30) is the system of record for per-tenant module
entitlements (the feature-flag store); Billing and Metering (Module 33)
keeps it in sync with pricing plans; and every *selectable* module
enforces its own entitlement by running `EntitlementGateMiddleware`,
whose reference implementation lives in Agent Cards
(`modules/agent-cards/src/agent_cards/security/entitlement_gate.py`).
This doc is the mechanical checklist for applying that same pattern to
the platform's other 27 selectable modules — the same shape this
platform already used to roll `ServiceAuthMiddleware` out to every
module from one first implementation.

Read this alongside:

- Multi-tenancy's README ("Per-tenant module entitlements: the
  platform's feature-flag store") for the entitlement data model and
  the `gate(tenant_id, module=...)` semantics.
- Billing and Metering's README ("Pricing is entitlement, not just a
  billing record") for how a tenant's plan becomes its entitlement set.
- Agent Cards' `security/entitlement_gate.py` docstring and
  `tests/unit/test_entitlement_gate.py` for the middleware itself and
  its full test matrix.

## Which modules this applies to

**Skip these 6 — the "Platform Base."** They're the platform itself,
not a selectable product module a subscription plan turns on or off,
so there's nothing to gate:

- Multi-tenancy (Module 30) — *is* the entitlement store
- Identity and Access (Module 31) — every request's authorization
  depends on it; it cannot depend on itself being entitled
- Auditability (Module 20) — every governance module's evidence
  layer
- Billing and Metering (Module 33) — issuing the entitlement sync
  itself
- Secrets and Credential Management (Module 32) — platform-wide
  credential issuance
- SDK and Developer Portal (Module 34) — the platform's own developer
  surface, not a tenant-facing product feature

**Already done.** Agent Cards (Module 23) — the reference
implementation this playbook mirrors.

**The remaining 27 modules** (this rollout's scope), grouped by the
platform's own module-table taxonomy
(`docs/agentic-platform-final-module-table.md`):

| Category | Modules |
|---|---|
| Orchestration and Runtime | Workflow Engine, Conversational Engine, LLM Gateway, Tool Orchestration |
| Intelligence Layer | Intent Detection, Agentic RAG, Context Engineering |
| Data Layer | Data Source Plugins, Knowledge Base, Vector DB, Graph DB |
| Memory | Short-Term Memory, Long-Term Memory |
| Governance and Safety | Guardrails, Sentinel Agents, Human Oversight, Regulatory and Compliance |
| Quality and Trust | Evaluation Framework, Observability |
| Interoperability | MCP, A2A |
| Agent Lifecycle and Ops | Agent Marketplace, LLMOps, FinOps, Deployment Strategy, Multi-modality, PromptOps |

(27 modules; Agent Cards, also in "Agent Lifecycle and Ops" in the
module table, is excluded here since it's already done.)

## The mechanical steps, per module

Everything below is a copy of the exact diff Agent Cards already
carries, with `agent_cards`/`AGENT_CARDS_`/`agent-cards` swapped for
the target module's own package name, env prefix, and `service_name`.
No new design decisions — if a step here looks like it needs one,
something about the target module doesn't match the assumed shape;
stop and check `ServiceAuthMiddleware`'s own rollout for how that
module already deviates, since the two middlewares share the same
`_EXCLUDED_PATHS` / dispatch-per-request shape.

1. **Copy the middleware file.** `security/entitlement_gate.py` verbatim,
   with the import path and `logger = get_logger(...)` line's package
   name updated. Nothing else in the file is module-specific — it reads
   `module_name` as a constructor argument, not a hardcoded string.

2. **Add two config fields**, next to the module's existing peer
   `_base_url` settings in `config.py`:

   ```python
   multi_tenancy_base_url: str = "http://localhost:8109"
   entitlement_gate_cache_ttl_seconds: float = 30.0
   ```

3. **Wire it into `main.py`**, immediately before the existing
   `app.add_middleware(ServiceAuthMiddleware, ...)` call (order
   matters — see the middleware's own docstring for why earlier-added
   runs *later*, so auth still executes first):

   ```python
   from <package>.security.entitlement_gate import EntitlementGateMiddleware
   ...
   app.add_middleware(
       EntitlementGateMiddleware,
       module_name=settings.service_name,
       multi_tenancy_base_url=settings.multi_tenancy_base_url,
       issuer=settings.service_name,
       shared_secret=settings.jwt_shared_secret,
       cache_ttl_seconds=settings.entitlement_gate_cache_ttl_seconds,
   )
   app.add_middleware(
       ServiceAuthMiddleware, audience=settings.service_name, shared_secret=settings.jwt_shared_secret,
   )
   ```

4. **Deploy wiring**: add `<PREFIX>_MULTI_TENANCY_BASE_URL` (and
   optionally `<PREFIX>_ENTITLEMENT_GATE_CACHE_TTL_SECONDS`) to
   `deploy/docker-compose.yml` (pointed at that module's own
   `dependency-stub`) and to the Helm chart's `values.yaml` +
   `templates/deployment.yaml` (pointed at
   `http://multi-tenancy:8109` in a real cluster).

5. **Dependency-stub**: add the always-allow gate stub —

   ```python
   @app.get("/v1/multi-tenancy/tenants/{tenant_id}/gate")
   async def gate(tenant_id: str, module: str | None = None) -> dict:
       return {"allowed": True, "reason": "active"}
   ```

   — so the module's own Deployability and Testability Contract keeps
   working standalone, with no real Multi-tenancy deployed alongside it.

6. **Tests**: copy `tests/unit/test_entitlement_gate.py` verbatim
   (it only imports the middleware and builds its own throwaway FastAPI
   app — nothing else in it is Agent-Cards-specific beyond the
   `MODULE_NAME` constant and the import path).

7. **README**: add the same "This module carries..." paragraph
   Agent Cards' README has (or, for every module *except* Agent Cards,
   a one-line pointer instead: "*Enforces its own subscription
   entitlement via `EntitlementGateMiddleware` — see Agent Cards'
   README and this playbook for the shared implementation.*"), plus a
   `security/` layout-table line for the new file.

8. **Verify**: `ruff check src tests` and `pytest tests/unit -q` green
   before committing — this platform's standard bar for every change.

## Why per-module, not a shared library

Every module in this platform already vendors its own
`security/jwt_auth.py` rather than importing a shared package — a
deliberate choice (see any module's own `jwt_auth.py` docstring) so
each module stays independently deployable with zero cross-module
import coupling, the same reasoning `ResilientHTTPClient` and
`ServiceAuthMiddleware` were copied module-to-module for. This
middleware follows the identical convention: copy, don't import.

## Sequencing

This rollout is independent per module and can happen in any order or
be done incrementally — each module's own `gate()` check is a no-op
(allows everything) until Multi-tenancy actually has that tenant's
entitlements configured (`entitlements_configured_at is not None`), so
there is no cross-module ordering dependency and no big-bang cutover
required. A reasonable order is highest business value first: the
modules customers most directly associate with a specific pricing tier
(Guardrails, Agentic RAG, Knowledge Base, Sentinel Agents) before
lower-visibility infrastructure modules (Graph DB, Vector DB).
