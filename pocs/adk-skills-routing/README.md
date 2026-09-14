# ADK Skill Routing PoC — deterministic skill selection for agents

A small, standalone proof of concept. It is **not** a Tectonic module (no
FastAPI service, no Postgres, nothing deployable) — it lives under `pocs/`
because it proves an architectural pattern that several Tectonic modules
(`tool-orchestration`, `agent-marketplace`, `sentinel-agents`) will
eventually need to make a real decision about, without committing any of
those modules' code to it yet.

## The question this answers

In a Google Agent Development Kit (ADK) multi-agent system, when an agent
has several skills available to it, **who decides which skill it uses for
a given job — the agent's own model, or something outside it?**

Those are different systems with different guarantees:

| | Agent decides | External router decides |
|---|---|---|
| How skill choice is verified | Statistically (prompt-eval, sampling) | Deterministically (a lookup either matches the routing table or it doesn't) |
| What changes skill choice | A prompt/model change, which can drift | A data change to the routing table |
| What an auditor can point to | "the model was instructed to..." | "job type X always resolves to skill Y, provably, here is the log" |
| Failure mode | Model picks a plausible-but-wrong skill | Router raises on an unmapped job type |

Regulated, auditable agentic systems need the right-hand column for
anything where "the agent used the correct capability for this job" is
itself a control, not just a UX nicety. This PoC builds and empirically
proves that column, then names what it deliberately leaves out.

## Design

```
job {job_type, payload}
        │
        ▼
 ROUTING_TABLE[job_type]  ──►  {agent_id, skill_id}      ← plain dict lookup.
        │                                                   No LLM call here.
        ▼
 build_agent_for_job(agent_id, skill_id)
        │  binds persona (agent) + instruction + tools (skill)
        │  onto a freshly constructed LlmAgent for this one job
        ▼
 InMemoryRunner.run_async(...)   ← the agent runs with ONLY the routed
        │                          skill's tool(s) in its context
        ▼
 audit record {job_id, job_type, agent, skill, tool_called,
               tools_visible_to_model, output}
```

Five pieces, each with a single job:

- **Agent** (`BASE_AGENTS`) — a stable identity/persona (`CaseWorkerAgent`,
  `QAAgent`). Knows nothing about any skill.
- **Skill** (`SKILLS`) — an instruction fragment + exactly the tool(s) one
  kind of job needs. Knows nothing about any agent or route. Reusable
  across agents.
- **Router** (`ROUTING_TABLE`) — a `job_type -> {agent, skill}` dict. The
  *only* place a skill is chosen, and it never calls a model to decide.
- **Binder** (`build_agent_for_job`) — constructs one `LlmAgent` per job,
  wiring in only the routed skill's instruction and tool(s). This is the
  enforcement point: the model literally cannot see a tool it wasn't
  routed to, because the binder never put it in `tools=[...]`.
- **Audit log** — one record per job. Every claim below is checked against
  it with an `assert`, not just asserted in prose.

## What the notebook proves (with real ADK, running code, asserted results)

1. **One agent, several job types, several skills** — `CaseWorkerAgent`
   handles three distinct job types via three distinct skills, resolved
   purely from `ROUTING_TABLE`; the model is never asked to choose.
2. **Deterministic and reproducible** — the same `job_type`, run six times
   with six different payloads, resolves to the identical
   `(agent, skill, tool_called)` triple every time.
3. **Tool isolation (negative control)** — for a given job, the tools
   *actually visible to the model* (captured straight from ADK's
   `LlmRequest.tools_dict` via a `before_model_callback`) contain the
   routed skill's tool and nothing else. Isolation is structural, not a
   prompt instruction the model could ignore.
4. **Dynamic at runtime** — mutating `ROUTING_TABLE` in place (standing in
   for an ops/config change) and re-running the *same* `job_type`
   resolves to a different agent and skill immediately — no agent code,
   model, or deployment changed.
5. **Many-to-many, not disguised 1:1** — the full audit log shows at least
   one agent used more than one skill, and at least one job type resolved
   to more than one agent (across the runtime change in step 4).

## Why the model is a stub, not live Gemini

This was built and executed in a network-restricted sandbox with no
`GOOGLE_API_KEY`. The property under test — is skill selection
deterministic and externally controllable — is a fact about the
routing/binding code, not about model output quality, so a small
`BaseLlm` subclass (`DeterministicStubLlm`, using ADK's own
`generate_content_async` extension point) always calls whichever single
tool it has been given and returns the result. Swapping in
`Gemini(model="gemini-2.5-flash")` with a real API key is a one-line
change per agent construction site — the routing/binding/audit logic does
not change. That swap is not exercised here and would need to be, before
treating a real model's tool-call reliability as validated by this PoC.

## Running it

```bash
cd pocs/adk-skills-routing
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m ipykernel install --user --name adk-poc --display-name adk-poc
jupyter notebook adk_skills_routing_poc.ipynb   # or: jupyter lab
```

The committed notebook already carries real output from an actual run
(`google-adk==2.9.0`) — you don't have to execute it to see the result,
but every cell is reproducible offline.

## What this does not prove (scope, named explicitly)

- **No live model call.** See above — this validates routing/binding
  mechanics, not a real Gemini model's tool-selection accuracy or latency.
- **No persistence.** `ROUTING_TABLE` is an in-memory dict. A production
  version needs a versioned, access-controlled store (e.g. a
  routing-policy table with an audit/outbox event per change — the shape
  this repository's `auditability` and `regulatory-compliance` modules
  already use for other kinds of decisions), not a module-level Python
  dict.
- **One tool per skill.** Real skills will often need several related
  tools and few-shot examples; the fix is `Skill.tool_fns: list[Callable]`
  and fanning `tools=[...]` over all of them in the binder — the pattern
  is unchanged, just not exercised here.
- **No "no route found" handling.** An unmapped `job_type` raises
  `KeyError` today. Production needs an explicit, logged failure mode.
- **No concurrency / multi-tenant stress test.** Jobs run sequentially,
  each against its own fresh agent and session.
- **No authorization control on who can change the routing table.**
  Hot-swapping a dict (proof 4) stands in for a real routing-policy
  change; it is not a substitute for access control and its own audit
  trail on that change.

## Relationship to Tectonic's modules

This does not modify, and is not wired into, any of the 34 modules under
`modules/`. It is offered as a validated pattern for whichever module ends
up owning cross-agent skill dispatch — most plausibly `tool-orchestration`
(module 4, which already owns tool discovery/invoke) or `agent-marketplace`
(module 24, which already owns agent/skill registration) — when that
design work is undertaken. No module README has been changed; adopting
this pattern into a real module is out of scope for this PoC.
