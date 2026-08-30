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

**Status: the base rollout below is complete.** All 28 selectable
modules (Agent Cards plus the 27 listed under "Which modules this
applies to") carry `security/entitlement_gate.py` and wire it into
`main.py`, confirmed by direct inspection — the "remaining 27" framing
further down predates that completion and is kept as-is below only as
the original mechanical checklist (still accurate as *documentation of
what each module's copy looks like*, just not as a live TODO list
anymore). See "Bounded-staleness cache upgrade" below for the one
change that is genuinely still in progress today: the base rollout gave
every module an unconditional-fail-open version of this middleware,
and that version is now being superseded, module by module, by a
bounded-staleness one.

## Bounded-staleness cache upgrade (2026-08-30)

The base rollout's `EntitlementGateMiddleware` failed open, unconditionally
and indefinitely, on any Multi-tenancy outage — a prolonged outage
silently and permanently disabled entitlement enforcement for as long as
it lasted, with no way for an operator to see it happening. The
independent architecture assessment flagged this as a P0 Phase 1A
closure item; it is not the same gap as the base rollout above and is
tracked separately here.

The fix (reference implementation now in **Agent Cards** and
**Conversational Engine** — two modules, deliberately, since this
touches genuinely shared, security-relevant logic and a second
implementation is cheap insurance that the first wasn't accidentally
module-specific):

- The middleware now distinguishes a decision it has itself **verified**
  via a real, successful Multi-tenancy call from one it is merely
  **caching**. A verified decision is served immediately within
  `cache_ttl_seconds` (unchanged from before), and — new — is *still*
  served for up to `entitlement_gate_max_staleness_seconds` after that if
  Multi-tenancy becomes unreachable, rather than the previous cache
  simply going stale and the code path falling through to a blind
  "allow".
- Once no verified decision is available within that bounded window (a
  cold cache with Multi-tenancy already down, or an outage that has
  outlasted the staleness bound), the request is now **denied** —
  `402`, "entitlement service unavailable and no recent verified
  decision cached". This is the one real behaviour change: fail-open is
  now bounded in time and grounded in a real prior decision, not
  unconditional.
- Each cached decision is HMAC-signed (the same shared secret already
  used for service-to-service JWTs) so a corrupted or forged cache entry
  is never trusted as verified.
- Two new Prometheus counters (`entitlement_gate_stale_served_total`,
  `entitlement_gate_fail_closed_total`, labelled by `module`) make both
  outcomes of a real outage observable — previously neither was, since
  the old version's fail-open was silent beyond a log line.
- New config field: `entitlement_gate_max_staleness_seconds` (default
  `300.0`), alongside the existing `entitlement_gate_cache_ttl_seconds`.

**Not yet done:** the other 26 modules under "Which modules this
applies to" below still carry the base rollout's unconditional-fail-open
version of `entitlement_gate.py`. Porting this upgrade to them is
mechanical (copy the file + test file, add the one config field, pass
`max_staleness_seconds=settings.entitlement_gate_max_staleness_seconds`
at the `main.py` call site — the identical diff between Agent Cards'
and Conversational Engine's copies) but is explicitly out of scope for
this pass, consistent with this platform's own "reference implementation
in one or two modules first" convention (the same shape the base
rollout below, and `ServiceAuthMiddleware` before it, were done in).

**Also not yet done, a related but distinct gap:** `QuotaEnforcementService`
consumers (LLM Gateway's `requests_per_minute` check, Vector DB's
`vector_count` check, both via `HTTPMultiTenancyClient`) still fail open
unconditionally on any Multi-tenancy error, the same pre-upgrade posture
this file's middleware used to have. The bounded-staleness pattern above
is the template for fixing that too, but the two call sites are shaped
differently (a quota check, not a binary gate) and were not touched in
this pass.

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

2. **Add config fields**, next to the module's existing peer
   `_base_url` settings in `config.py`:

   ```python
   multi_tenancy_base_url: str = "http://localhost:8109"
   entitlement_gate_cache_ttl_seconds: float = 30.0
   # Only present in modules that have taken the bounded-staleness cache
   # upgrade (see that section above) -- Agent Cards and Conversational
   # Engine today, not yet the other 26 modules.
   entitlement_gate_max_staleness_seconds: float = 300.0
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
