#!/usr/bin/env python3
"""Seeds one real tenant per subscription tier fixture in
`test-data/subscription-tiers/` against real, running module APIs --
Multi-tenancy, Billing and Metering, and Identity and Access -- so the
platform's subscription model (see `docs/entitlement-gate-rollout.md`
and the root README's "Subscription model and the entitlement gate")
has real, inspectable test data behind it instead of only a design
artifact.

For each tier fixture with a `billing` block (starter/growth/enterprise/
custom): registers a tenant, then creates a tenant-specific pricing plan
for it. Billing and Metering's own `PricingPlanService.create` then
syncs that plan's module list to Multi-tenancy automatically -- this
script never calls Multi-tenancy's entitlements endpoint directly for
those tiers, the same real code path a paying customer's plan takes.

For the one fixture with a `direct_entitlements` block instead (demo,
tier="sandbox"): there is no pricing plan to derive entitlements from
-- a trial tenant doesn't get billed -- so this script sets its
entitlements directly via Multi-tenancy's own `POST
/tenants/{id}/entitlements`, exactly the path a real sandbox-onboarding
flow would take.

Every fixture also gets one admin identity registered against Identity
and Access, scoped to that tenant via `X-Tenant-Id`, using a shared
"tenant-admin" role this script creates once (idempotent -- a second
run's duplicate-role attempt is logged and skipped, not fatal).

Zero third-party dependencies: HTTP via `urllib.request`, JWT (HS256)
minted by hand -- the same three-claim shape (`iss`/`aud`/`iat`/`exp`)
every module's own `security/jwt_auth.py::mint_service_token` produces,
verified byte-for-byte against `verify_service_token` in this
platform's test suites -- so this script runs with nothing but a
stdlib Python 3.11+ interpreter.

Usage:
    TECTONIC_JWT_SHARED_SECRET=<shared secret, if not the dev default> \\
        python3 scripts/seed_subscription_tiers.py

Expects Multi-tenancy (default :8109), Billing and Metering (:8112) and
Identity and Access (:8110) already running -- e.g. each module's own
`docker compose -f deploy/docker-compose.yml up`, or a shared
docker-compose stack with all three. Override any base URL with
MULTI_TENANCY_URL / BILLING_URL / IDENTITY_ACCESS_URL.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "test-data" / "subscription-tiers"
FIXTURE_ORDER = ["starter.json", "growth.json", "enterprise.json", "custom.json", "demo.json"]

MULTI_TENANCY_URL = os.environ.get("MULTI_TENANCY_URL", "http://localhost:8109")
BILLING_URL = os.environ.get("BILLING_URL", "http://localhost:8112")
IDENTITY_ACCESS_URL = os.environ.get("IDENTITY_ACCESS_URL", "http://localhost:8110")

# The same insecure, obviously-a-placeholder default every module's own config.py falls
# back to -- overridden the same way every module is: TECTONIC_JWT_SHARED_SECRET.
JWT_SHARED_SECRET = os.environ.get("TECTONIC_JWT_SHARED_SECRET", "dev-insecure-shared-secret-change-me")
ISSUER = "seed-subscription-tiers"

TENANT_ADMIN_ROLE = {
    "name": "tenant-admin",
    "scopes": ["tenant:admin", "billing:read", "billing:write", "identities:manage"],
    "description": "Full administrative access within one tenant -- seeded by scripts/seed_subscription_tiers.py.",
}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def mint_service_token(*, audience: str, ttl_seconds: int = 300) -> str:
    """HS256, matching every module's own `mint_service_token` exactly:
    header {"alg": "HS256", "typ": "JWT"}, payload {iss, aud, iat, exp}."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {"iss": ISSUER, "aud": audience, "iat": now, "exp": now + ttl_seconds}
    signing_input = (
        f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}."
        f"{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    signature = hmac.new(JWT_SHARED_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


class ApiError(RuntimeError):
    def __init__(self, method: str, url: str, status: int, body: Any) -> None:
        super().__init__(f"{method} {url} -> {status}: {body}")
        self.status = status
        self.body = body


def call(
    method: str, url: str, *, audience: str, json_body: dict | None = None, tenant_id: str | None = None,
) -> Any:
    data = json.dumps(json_body).encode() if json_body is not None else None
    headers = {"Authorization": f"Bearer {mint_service_token(audience=audience)}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if tenant_id is not None:
        headers["X-Tenant-Id"] = tenant_id

    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        body = json.loads(raw) if raw else None
        raise ApiError(method, url, exc.code, body) from exc


def ensure_tenant_admin_role() -> None:
    try:
        call("POST", f"{IDENTITY_ACCESS_URL}/v1/identity-access/roles", audience="identity-access", json_body=TENANT_ADMIN_ROLE)
        print(f"  [identity-access] created role {TENANT_ADMIN_ROLE['name']!r}")
    except ApiError as exc:
        # Not idempotent by design (core/role_service.py) -- a second run hitting a
        # duplicate name is expected, not a failure; anything else still is.
        print(f"  [identity-access] role {TENANT_ADMIN_ROLE['name']!r} already exists or rejected ({exc.status}), continuing")


def seed_fixture(path: Path) -> dict[str, Any]:
    fixture = json.loads(path.read_text())
    tier = fixture["tier"]
    print(f"\n=== {tier} ({fixture['tenant_name']}) ===")

    tenant = call(
        "POST", f"{MULTI_TENANCY_URL}/v1/multi-tenancy/tenants", audience="multi-tenancy",
        json_body={"name": fixture["tenant_name"], "tier": tier},
    )
    tenant_id = tenant["id"]
    print(f"  [multi-tenancy] tenant {tenant_id} (tier={tier})")

    if "billing" in fixture:
        billing = fixture["billing"]
        plan = call(
            "POST", f"{BILLING_URL}/v1/billing/pricing-plans", audience="billing-and-metering",
            json_body={"tenant_id": tenant_id, "name": billing["plan_name"], "unit_prices": billing["unit_prices"]},
        )
        module_fees = {k: v for k, v in billing["unit_prices"].items() if k != "llm.cost_usd"}
        monthly_total = sum(module_fees.values())
        print(f"  [billing] plan {plan['id']} ({billing['plan_name']}): {len(module_fees)} modules, ${monthly_total}/mo base")
    else:
        module_names = fixture["direct_entitlements"]
        call(
            "POST", f"{MULTI_TENANCY_URL}/v1/multi-tenancy/tenants/{tenant_id}/entitlements",
            audience="multi-tenancy", json_body={"module_names": module_names},
        )
        print(f"  [multi-tenancy] set {len(module_names)} entitlements directly (no pricing plan -- sandbox tier)")

    entitlements = call(
        "GET", f"{MULTI_TENANCY_URL}/v1/multi-tenancy/tenants/{tenant_id}/entitlements", audience="multi-tenancy",
    )
    print(f"  [multi-tenancy] verified: configured={entitlements['configured']}, {len(entitlements['module_names'])} modules entitled")

    admin = fixture["admin_identity"]
    identity = call(
        "POST", f"{IDENTITY_ACCESS_URL}/v1/identity-access/identities", audience="identity-access",
        tenant_id=tenant_id, json_body=admin,
    )
    print(f"  [identity-access] admin identity {identity['id']} ({identity['name']})")

    return {
        "tier": tier, "tenant_id": tenant_id, "tenant_name": fixture["tenant_name"],
        "module_count": len(entitlements["module_names"]), "admin_identity_id": identity["id"],
    }


def main() -> int:
    ensure_tenant_admin_role()

    results = []
    for filename in FIXTURE_ORDER:
        path = FIXTURES_DIR / filename
        if not path.is_file():
            print(f"skipping missing fixture: {path}", file=sys.stderr)
            continue
        try:
            results.append(seed_fixture(path))
        except ApiError as exc:
            print(f"  FAILED: {exc}", file=sys.stderr)
            return 1

    print("\n=== Summary ===")
    for r in results:
        print(f"  {r['tier']:<10} tenant={r['tenant_id']}  modules={r['module_count']:>2}  admin={r['admin_identity_id']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
