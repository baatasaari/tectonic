#!/usr/bin/env python3
"""Seeds the Phase 2 support-agent product slice's own demo data (ticket
#82, docs/phase2-product-slice-01-support-agent.md) against real, running
module APIs: a real Acme Corp tenant + Growth-plan entitlements
(Multi-tenancy), a real end-user identity (Identity and Access), a real
indexed knowledge base document (Knowledge Base/Vector DB), a real intent
taxonomy (Intent Detection), and LLM Gateway's own real provider/
budget-policy/virtual-key provisioning (ticket #82's own new admin
routes) pointed at this slice's mock external-systems stub -- following
the same "seed against real running module APIs" pattern
scripts/seed_subscription_tiers.py already established, not a new
fixtures format.

Writes /tmp/support_agent_seed_output.json with everything the next
stages need: the real virtual_key_id (Workflow Engine needs this baked
into its own env before it starts -- see
scripts/product-slice-stubs/stack.py's own module docstring for why) and
the real tool_id (the workflow definition's own tool_refs needs this --
see scripts/post_support_agent_definition.py).

Zero third-party dependencies -- same stdlib-only design as
seed_subscription_tiers.py.

Usage:
    python3 scripts/seed_support_agent_demo.py
Expects every module in the slice already running -- see
scripts/product-slice-stubs/stack.py.
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
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

OUTPUT_PATH = Path(os.environ.get("SUPPORT_AGENT_SEED_OUTPUT", "/tmp/support_agent_seed_output.json"))

MULTI_TENANCY_URL = os.environ.get("MULTI_TENANCY_URL", "http://localhost:8109")
IDENTITY_ACCESS_URL = os.environ.get("IDENTITY_ACCESS_URL", "http://localhost:8110")
LLM_GATEWAY_URL = os.environ.get("LLM_GATEWAY_URL", "http://localhost:8082")
TOOL_ORCHESTRATION_URL = os.environ.get("TOOL_ORCHESTRATION_URL", "http://localhost:8083")
BILLING_URL = os.environ.get("BILLING_URL", "http://localhost:8112")
KNOWLEDGE_BASE_URL = os.environ.get("KNOWLEDGE_BASE_URL", "http://localhost:8088")
INTENT_DETECTION_URL = os.environ.get("INTENT_DETECTION_URL", "http://localhost:8084")
MOCK_STUB_URL = os.environ.get("MOCK_STUB_URL", "http://localhost:9200")

JWT_SHARED_SECRET = os.environ.get("TECTONIC_JWT_SHARED_SECRET", "dev-insecure-shared-secret-change-me")
ISSUER = "seed-support-agent-demo"

TENANT_NAME = "Acme Corp"
ADMIN_ROLE = {
    "name": "tenant-admin",
    "scopes": ["tenant:admin", "billing:read", "billing:write", "identities:manage"],
    "description": "Full administrative access within one tenant -- seeded by scripts/seed_subscription_tiers.py.",
}
CUSTOMER_ROLE = {
    "name": "acme-customer",
    "scopes": ["support:chat"],
    "description": "An Acme Corp end customer, authenticated to talk to the support agent -- seeded by scripts/seed_support_agent_demo.py.",
}

# Every module this slice's own critical path names (docs/phase2-product-slice-01-support-agent.md's
# module table), keyed by each module's own real service_name / EntitlementGateMiddleware module_name.
SLICE_MODULE_NAMES = [
    "identity-and-access", "multi-tenancy", "conversational-engine", "workflow-engine",
    "intent-detection", "agentic-rag", "knowledge-base", "vector-db", "tool-orchestration",
    "llm-gateway", "guardrails", "human-oversight", "billing-and-metering", "auditability", "observability",
]

RETURN_POLICY_DOCUMENT = (
    "Acme Corp Return Policy: Items may be returned within 30 days of delivery for a full refund, "
    "provided they are unused and in original packaging. Refunds are issued to the original payment "
    "method within 5-7 business days of us receiving the returned item."
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def mint_service_token(*, audience: str, ttl_seconds: int = 300) -> str:
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
    method: str, url: str, *, audience: str, json_body: dict | None = None,
    form_body: dict | None = None, tenant_id: str | None = None,
) -> Any:
    data: bytes | None = None
    headers = {"Authorization": f"Bearer {mint_service_token(audience=audience)}"}
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif form_body is not None:
        data = urllib.parse.urlencode(form_body).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if tenant_id is not None:
        headers["X-Tenant-Id"] = tenant_id

    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            body = raw.decode(errors="replace")  # an unhandled 500 comes back as plain text, not JSON
        raise ApiError(method, url, exc.code, body) from exc


def ensure_role(role: dict) -> None:
    try:
        call("POST", f"{IDENTITY_ACCESS_URL}/v1/identity-access/roles", audience="identity-access", json_body=role)
        print(f"  [identity-access] created role {role['name']!r}")
    except ApiError as exc:
        print(f"  [identity-access] role {role['name']!r} already exists or rejected ({exc.status}), continuing")


def phase1() -> dict:
    """Everything that doesn't need Vector DB running yet -- see
    scripts/product-slice-stubs/stack.py's own module docstring for why
    this is split from phase2 (Vector DB itself needs the real virtual
    key this phase creates, baked into its own env, before it can even
    start)."""
    print(f"=== {TENANT_NAME} (phase 1) ===")

    tenant = call(
        "POST", f"{MULTI_TENANCY_URL}/v1/multi-tenancy/tenants", audience="multi-tenancy",
        json_body={"name": TENANT_NAME, "tier": "growth"},
    )
    tenant_id = tenant["id"]
    print(f"  [multi-tenancy] tenant {tenant_id}")

    call(
        "POST", f"{MULTI_TENANCY_URL}/v1/multi-tenancy/tenants/{tenant_id}/entitlements",
        audience="multi-tenancy", json_body={"module_names": SLICE_MODULE_NAMES},
    )
    print(f"  [multi-tenancy] entitled to {len(SLICE_MODULE_NAMES)} modules")

    # Billing and Metering's own `meter_tenant()` only ever looks up a
    # tenant-specific `PricingPlan` (never the module's separate global-
    # default one) -- the same "seed the tenant its own real plan" step
    # scripts/seed_subscription_tiers.py already established, just missing
    # here until ticket #82's own end-to-end verification surfaced it (a
    # 404 from `meter_tenant`, not a module bug). A second, more serious
    # gap that same verification surfaced: `PricingPlanService.create()`
    # doesn't just create a plan, it *syncs* Multi-tenancy's entitlements
    # to exactly the module names in `unit_prices` (see that service's own
    # docstring) -- creating a plan with only `{"conversational-engine":
    # ...}` here silently clobbered the entitlements grant immediately
    # above down to that one module, breaking every other module's own
    # entitlement gate for the rest of this seed run. `unit_prices` must
    # name every module this tenant needs entitled, matching
    # SLICE_MODULE_NAMES exactly, not just the one module whose usage
    # this slice's own conversations happen to generate a real non-zero
    # count for (every other module's own metered quantity is a real,
    # honestly-computed zero, not a fabricated one).
    call(
        "POST", f"{BILLING_URL}/v1/billing/pricing-plans", audience="billing-and-metering",
        json_body={
            "tenant_id": tenant_id, "name": "Acme Corp Support Agent Plan",
            "unit_prices": {name: 0.01 for name in SLICE_MODULE_NAMES},
        },
    )
    print(f"  [billing-and-metering] pricing plan created ({len(SLICE_MODULE_NAMES)} metered resources)")

    ensure_role(ADMIN_ROLE)
    ensure_role(CUSTOMER_ROLE)

    end_user = call(
        "POST", f"{IDENTITY_ACCESS_URL}/v1/identity-access/identities", audience="identity-access",
        tenant_id=tenant_id, json_body={"name": "Acme Customer", "type": "user", "role_names": [CUSTOMER_ROLE["name"]]},
    )
    print(f"  [identity-access] end-user identity {end_user['id']}")

    token = call(
        "POST", f"{IDENTITY_ACCESS_URL}/v1/identity-access/tokens", audience="identity-access",
        json_body={"identity_id": end_user["id"], "requested_scopes": ["support:chat"], "ttl_seconds": 3600},
    )
    print(f"  [identity-access] issued a real end-user token (scopes={token['granted_scopes']})")

    try:
        provider = call(
            "POST", f"{LLM_GATEWAY_URL}/v1/llm-gateway/admin/providers", audience="llm-gateway",
            json_body={"provider_name": "acme-mock-llm", "endpoint": MOCK_STUB_URL, "priority": 1},
        )
        print(f"  [llm-gateway] provider {provider['provider_name']!r} -> {MOCK_STUB_URL}")
    except ApiError as exc:
        if exc.status != 409:
            raise
        providers = call("GET", f"{LLM_GATEWAY_URL}/v1/llm-gateway/admin/providers", audience="llm-gateway")
        provider = next(p for p in providers if p["provider_name"] == "acme-mock-llm")
        print(f"  [llm-gateway] provider {provider['provider_name']!r} already configured, reusing")

    budget = call(
        "POST", f"{LLM_GATEWAY_URL}/v1/llm-gateway/admin/budget-policies", audience="llm-gateway",
        json_body={"tenant_id": tenant_id, "period": "monthly", "limit_amount": 1000.0, "alert_threshold_pct": 0.8},
    )
    print(f"  [llm-gateway] budget policy {budget['id']} (${budget['limit_amount']}/mo)")

    virtual_key = call(
        "POST", f"{LLM_GATEWAY_URL}/v1/llm-gateway/admin/virtual-keys", audience="llm-gateway",
        json_body={"tenant_id": tenant_id, "provider_scope": [], "budget_policy_ref": budget["id"]},
    )
    print(f"  [llm-gateway] virtual key {virtual_key['id']}")

    tool = call(
        "POST", f"{TOOL_ORCHESTRATION_URL}/v1/tool-orchestration/tools", audience="tool-orchestration",
        tenant_id=tenant_id, json_body={
            "name": "get_order_status", "mcp_server_ref": f"{MOCK_STUB_URL}/mcp",
            "schema": {"input": {"order_id": "string"}, "output": {"status": "string", "eta": "string"}},
        },
    )
    print(f"  [tool-orchestration] registered tool {tool['id']} ({tool['name']}, status={tool['status']})")

    taxonomy = call(
        "POST", f"{INTENT_DETECTION_URL}/v1/intent-detection/taxonomies", audience="intent-detection",
        json_body={
            "tenant_id": tenant_id,
            "intents": [
                {
                    "name": "policy_question", "description": "A question about store policy",
                    "examples": ["What's your return policy?", "How long do I have to return an item?", "Can I get a refund?"],
                },
                {
                    "name": "order_status", "description": "A question about an existing order's status",
                    "examples": ["Where's my order #A1029?", "Has my order shipped yet?", "What's the status of my order?"],
                },
                {
                    "name": "refund_request", "description": "A request for a refund on a specific order",
                    "examples": ["I want a refund for order #A1029, it's $850.", "Please refund my $850 order.", "I'd like my money back for this order."],
                },
            ],
        },
    )
    print(f"  [intent-detection] taxonomy {taxonomy['id']} v{taxonomy['version']} ({taxonomy['status']})")
    call(
        "POST", f"{INTENT_DETECTION_URL}/v1/intent-detection/taxonomies/{taxonomy['id']}/activate",
        audience="intent-detection",
    )
    print("  [intent-detection] taxonomy activated")

    output = {
        "tenant_id": tenant_id,
        "end_user_identity_id": end_user["id"],
        "end_user_token": token["token"],
        "llm_gateway_virtual_key_id": virtual_key["id"],
        "tool_id": tool["id"],
        "intent_taxonomy_id": taxonomy["id"],
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {OUTPUT_PATH}")
    return output


def phase2() -> dict:
    """Real document ingestion -- needs Vector DB running for real (see
    phase1's own docstring)."""
    output = json.loads(OUTPUT_PATH.read_text())
    tenant_id = output["tenant_id"]
    print(f"=== {TENANT_NAME} (phase 2) ===")

    doc = call(
        "POST", f"{KNOWLEDGE_BASE_URL}/v1/knowledge-base/documents", audience="knowledge-base",
        form_body={
            "tenant_id": tenant_id, "title": "Acme Corp Return Policy", "source_type": "upload",
            "content_text": RETURN_POLICY_DOCUMENT, "policy_tags": "[]",
        },
    )
    print(f"  [knowledge-base] ingested document {doc['document']['id']} ({doc['chunk_count']} chunks)")

    output["knowledge_base_document_id"] = doc["document"]["id"]
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {OUTPUT_PATH}")
    return output


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"
    if phase in ("phase1", "all"):
        phase1()
    if phase in ("phase2", "all"):
        phase2()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
