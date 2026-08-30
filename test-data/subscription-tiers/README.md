# Subscription tier test data

Five fixtures, one per subscription tier from the platform's own cost
calculator/design artifact (Starter, Growth, Enterprise, Custom, and the
public Demo/sandbox site), each a real tenant this platform's own APIs
can create end to end. See
[`docs/entitlement-gate-rollout.md`](../../docs/entitlement-gate-rollout.md)
and the root README's "Subscription model and the entitlement gate" for
the mechanism these fixtures exercise.

Seed all five against real, running module APIs:

```bash
python3 scripts/seed_subscription_tiers.py
```

See `scripts/seed_subscription_tiers.py`'s own docstring for
prerequisites (Multi-tenancy, Billing and Metering, and Identity and
Access reachable — each module's own `docker compose -f
deploy/docker-compose.yml up`, or a shared stack) and override knobs.
Verified against all three real module APIs (in-memory-repository test
servers, real HTTP, real JWTs) — every fixture round-trips end to end,
including Billing and Metering's real sync to Multi-tenancy's
entitlement store and Multi-tenancy's real `gate(tenant_id,
module=...)` correctly denying a module the tenant didn't pay for.

## The fixtures

| File | Tier | Modules | Monthly module fees | How entitlements land |
|---|---|---|---|---|
| `starter.json` | `starter` | 4 | $490 | Billing pricing plan → auto-synced |
| `growth.json` | `growth` | 12 | $1,260 | Billing pricing plan → auto-synced |
| `enterprise.json` | `enterprise` | 28 (all selectable modules) | $2,750 | Billing pricing plan → auto-synced |
| `custom.json` | `custom` | 13 | $1,560 | Billing pricing plan → auto-synced |
| `demo.json` | `sandbox` | 28 (all selectable modules) | none — no plan | Set directly via Multi-tenancy's entitlements endpoint |

All dollar figures are the illustrative flat per-module fees from the
platform's own cost-calculator design artifact — a demonstration
pricing model, not a commercial rate card. Every fixture also plugs into
the real per-tenant `"llm.cost_usd"` usage-metered rate Billing and
Metering already supports (see each `starter.json`/etc.'s own
`billing.unit_prices["llm.cost_usd"]`), on top of the flat module fees.

## Why Starter/Growth/Enterprise aren't hardcoded in the seed script

They're the same three presets the cost-calculator artifact ships
(`starter`/`growth`/`enterprise` in its own `PRESETS` object) — copied
here as data, not logic, so a tier's module list or pricing can change
without touching `scripts/seed_subscription_tiers.py` at all.

## Why `custom.json` isn't literally the calculator's "clear" preset

The calculator's fourth preset (`clear`) is a UI reset button — zero
modules selected, a starting point for hand-assembly, not a real plan
anyone would subscribe to. `custom.json` is what a buyer actually
produces from that starting point: a regulated-industry combination
(heavy on Guardrails/Sentinel Agents/Human Oversight/Regulatory and
Compliance) that doesn't match either preset, demonstrating the
platform really does support an arbitrary module selection per tenant,
not just the three named tiers.

## Why `demo.json` sets entitlements directly instead of through a plan

A public demo/trial tenant doesn't get billed, so there's no pricing
plan for Billing and Metering to derive an entitlement set from. This
mirrors SDK and Developer Portal (Module 34)'s own real convention:
registering a developer already tags their sandbox tenant with
`tier="sandbox"` as the queryable signal that separates trial tenants
from paying ones (see that module's README). `demo.json` extends the
same idea to entitlements — every module unlocked, set directly against
Multi-tenancy's `POST /tenants/{id}/entitlements`, the path a real
sandbox-onboarding flow would take.
